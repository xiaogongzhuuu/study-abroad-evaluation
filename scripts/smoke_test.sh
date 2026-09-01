#!/usr/bin/env bash
# D7 全链路冒烟测试：健康检查 → 参数校验 → 测评接口 → 留资接口 → 静态页面
# 用法：先启动服务，再执行 bash scripts/smoke_test.sh（可用 BASE_URL 覆盖地址）
set -u

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"
DB_PATH="${REPO_ROOT}/data/leads.db"

# 数据查看接口口令（.env 配置了 ADMIN_TOKEN 时需透传：TOKEN=xxx bash scripts/smoke_test.sh）
TOKEN_HEADER=()
if [ -n "${TOKEN:-}" ]; then
  TOKEN_HEADER=(-H "X-Admin-Token: ${TOKEN}")
fi

PASS=0
FAIL=0

check() {
  # check <描述> <实际输出> <期望包含的子串>
  local desc="$1" actual="$2" expected="$3"
  if echo "$actual" | grep -qF "$expected"; then
    echo "✅ ${desc}"
    PASS=$((PASS + 1))
  else
    echo "❌ ${desc}"
    echo "   期望包含：${expected}"
    echo "   实际输出：${actual}"
    FAIL=$((FAIL + 1))
  fi
}

check_status() {
  # check_status <描述> <实际状态码> <期望状态码>
  local desc="$1" actual="$2" expected="$3"
  if [ "$actual" = "$expected" ]; then
    echo "✅ ${desc}"
    PASS=$((PASS + 1))
  else
    echo "❌ ${desc}（期望 ${expected}，实际 ${actual}）"
    FAIL=$((FAIL + 1))
  fi
}

# 发请求并拆出状态码与响应体：响应体输出到 stdout 最后一行是状态码
# 用法：resp=$(request ...) ; body=${resp%$'\n'*} ; status=${resp##*$'\n'}
request() {
  curl -s --max-time 120 -w $'\n__STATUS__:%{http_code}' "$@"
}

echo "== 1. 健康检查 =="
resp=$(request "${BASE_URL}/health")
check "返回 ok" "${resp%$'\n'*}" '"status":"ok"'

echo "== 2. 测评接口参数校验 =="
# GPA 超范围
resp=$(request -X POST "${BASE_URL}/api/v1/evaluate" \
  -H 'Content-Type: application/json' \
  -d '{"gpa":6,"major":"计算机科学","target_country":"美国"}')
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "GPA 超范围 → 422" "${status#__STATUS__:}" 422
check "GPA 错误提示中文" "$body" "GPA"

# 缺少专业
resp=$(request -X POST "${BASE_URL}/api/v1/evaluate" \
  -H 'Content-Type: application/json' \
  -d '{"gpa":3.6,"target_country":"美国"}')
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "缺少专业 → 422" "${status#__STATUS__:}" 422
check "缺少专业提示中文" "$body" "申请专业"

echo "== 3. 测评接口真实调用（DeepSeek）=="
resp=$(request -X POST "${BASE_URL}/api/v1/evaluate" \
  -H 'Content-Type: application/json' \
  -d '{"gpa":3.6,"major":"计算机科学","target_country":"美国"}')
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "测评接口 → 200" "${status#__STATUS__:}" 200
check "返回冲刺档" "$body" "冲刺"
check "返回匹配档" "$body" "匹配"
check "返回保底档" "$body" "保底"
report_id=$(printf '%s' "$body" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("report_id", ""))' 2>/dev/null || true)
if [ -n "$report_id" ]; then
  echo "✅ 测评报告已获得服务端 report_id"
  PASS=$((PASS + 1))
else
  echo "❌ 测评响应缺少 report_id"
  FAIL=$((FAIL + 1))
fi

echo "== 4. 留资接口 =="
# 手机号格式错误
resp=$(request -X POST "${BASE_URL}/api/v1/leads" \
  -H 'Content-Type: application/json' \
  -d '{"wechat":"test_wx","phone":"123","gpa":3.6,"major":"计算机科学","target_country":"美国"}')
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "手机号格式错误 → 422" "${status#__STATUS__:}" 422
check "手机号错误提示中文" "$body" "手机号"

# 正常留资（通过服务端生成的 report_id 关联测评报告）
count_before=$(python3 -c "import sqlite3;print(sqlite3.connect('${DB_PATH}').execute('SELECT COUNT(*) FROM leads').fetchone()[0])" 2>/dev/null || echo 0)
resp=$(request -X POST "${BASE_URL}/api/v1/leads" \
  -H 'Content-Type: application/json' \
  -d "{\"wechat\":\"smoke_test\",\"phone\":\"13800138000\",\"gpa\":3.6,\"major\":\"计算机科学\",\"target_country\":\"美国\",\"school_tier\":\"985\",\"degree\":\"硕士\",\"language_type\":\"雅思\",\"language_score\":7,\"report_id\":\"${report_id}\"}")
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "正常留资 → 200" "${status#__STATUS__:}" 200
check "返回留资成功" "$body" "留资成功"
resp=$(request -H "X-Admin-Token: ${TOKEN:-}" "${BASE_URL}/api/v1/leads")
check "报告已通过 report_id 入库" "${resp%$'\n'*}" "$report_id"
count_after=$(python3 -c "import sqlite3;print(sqlite3.connect('${DB_PATH}').execute('SELECT COUNT(*) FROM leads').fetchone()[0])" 2>/dev/null || echo 0)
if [ "$count_after" -gt "$count_before" ]; then
  echo "✅ 留资数据已入库（${count_before} → ${count_after} 条）"
  PASS=$((PASS + 1))
else
  echo "❌ 留资数据未入库（${count_before} → ${count_after} 条）"
  FAIL=$((FAIL + 1))
fi

# 语言类型/成绩需成对填写
resp=$(request -X POST "${BASE_URL}/api/v1/leads" \
  -H 'Content-Type: application/json' \
  -d '{"wechat":"smoke_partial","phone":"13900139000","language_score":6.5}')
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "仅填语言成绩留资 → 422" "${status#__STATUS__:}" 422

echo "== 5. 数据查看接口 =="
resp=$(request -H "X-Admin-Token: ${TOKEN:-}" "${BASE_URL}/api/v1/leads")
body=${resp%$'\n'*}; status=${resp##*$'\n'}
check_status "线索列表 → 200" "${status#__STATUS__:}" 200
check "列表含新留资" "$body" "smoke_test"
check "列表含选填字段" "$body" "雅思"
resp=$(request "${BASE_URL}/admin.html")
check "数据查看页可访问" "${resp%$'\n'*}" "留资数据"

echo "== 6. 静态页面 =="
resp=$(request "${BASE_URL}/")
check "首页可访问" "${resp%$'\n'*}" "智能选校测评"

echo ""
echo "========== 结果：通过 ${PASS} 项，失败 ${FAIL} 项 =========="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi

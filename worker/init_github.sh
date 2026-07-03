#!/usr/bin/env bash

# init_github.sh
# 用法：
#   ./worker/init_github.sh <YOUR_GITHUB_REPO_URL>
#
# 功能：
# 1. 初始化 git repo
# 2. 设置默认分支 main
# 3. 绑定 origin 到用户提供的 GitHub repo URL

set -u

REPO_URL="${1:-}"

if [ -z "${REPO_URL}" ]; then
  echo "[init_github] 用法: $0 <YOUR_GITHUB_REPO_URL>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${ROOT_DIR}" || exit 1

echo "[init_github] 项目目录: ${ROOT_DIR}"

# 第一步：初始化 git repo。
if [ ! -d ".git" ]; then
  git init
else
  echo "[init_github] 已存在 .git，跳过 git init"
fi

# 第二步：设置默认分支为 main。
git branch -M main

# 第三步：绑定或更新 origin。
if git remote get-url origin >/dev/null 2>&1; then
  git remote set-url origin "${REPO_URL}"
  echo "[init_github] 已更新 origin: ${REPO_URL}"
else
  git remote add origin "${REPO_URL}"
  echo "[init_github] 已添加 origin: ${REPO_URL}"
fi

echo "[init_github] 初始化完成"
echo "[init_github] 下一步可以运行："
echo "  git add ."
echo "  git commit -m \"init agent loop\""
echo "  git push -u origin main"

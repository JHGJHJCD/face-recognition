#!/bin/bash
# בנייה + בדיקת עשן + commit/push + Release. שימוש (ברקע!):  bash dev/release.sh "הודעת commit" "הערות שחרור"
# הגרסה נלקחת מ-version.py. נעצר בכל כישלון; כל שלב מדפיס שורת סטטוס.
set -e
cd "$(dirname "$0")/.."
PY="/c/Users/יהודה/AppData/Local/Programs/Python/Python312/python.exe"
GH="/c/Users/יהודה/AppData/Local/gh_cli/bin/gh.exe"
REPO="JHGJHJCD/face-recognition"
VER=$("$PY" -c "import version; print(version.APP_VERSION)")
echo "[1/5] building v$VER"
taskkill //F //IM FaceID.exe >/dev/null 2>&1 || true
"$PY" -m PyInstaller --noconfirm --clean "זיהוי_פנים.spec" > build.log 2>&1
cp "dist/זיהוי_פנים.exe" dist/FaceID.exe
echo "[2/5] smoke test (clean folder with models junction)"
T="$(cygpath -w "$TEMP")\\faceid_test"
powershell -NoProfile -Command "\$T='$T'; if (-not (Test-Path \"\$T\\models\")) { New-Item -ItemType Directory -Force \$T | Out-Null; cmd /c mklink /J \"\$T\\models\" 'C:\\Users\\יהודה\\Desktop\\זיהוי פנים\\models' | Out-Null }; New-Item -ItemType Directory -Force \"\$T\\shots\" | Out-Null; Remove-Item \"\$T\\shots\\*\",\"\$T\\crash_log.txt\" -ErrorAction SilentlyContinue; Copy-Item 'C:\\Users\\יהודה\\Desktop\\זיהוי פנים\\dist\\FaceID.exe' \"\$T\\FaceID.exe\" -Force; \$p = Start-Process \"\$T\\FaceID.exe\" -ArgumentList \"--shot \`\"\$T\\shots\`\"\" -PassThru -WorkingDirectory \$T; \$p.WaitForExit(300000) | Out-Null; if (-not \$p.HasExited) { \$p.Kill() }; \$n = (Get-ChildItem \"\$T\\shots\").Count; if (\$n -lt 8 -or (Test-Path \"\$T\\crash_log.txt\")) { Write-Output \"SMOKE FAILED shots=\$n\"; exit 1 }; Write-Output \"smoke ok shots=\$n\""
echo "[3/5] commit + push"
git add -A
git commit -q -m "$1" || true
git push -q
echo "[4/5] release upload"
"$GH" release create "v$VER" -R $REPO --draft --title "זיהוי פנים $VER" --notes "$2" >/dev/null
for n in 1 2 3; do "$GH" release upload "v$VER" dist/FaceID.exe -R $REPO --clobber && break; sleep 20; done
"$GH" release edit "v$VER" -R $REPO --draft=false --latest >/dev/null
echo "[5/5] DONE: $("$GH" release view "v$VER" -R $REPO --json assets,isDraft -q '"draft=\(.isDraft) \(.assets[0].name) \(.assets[0].size)"')"

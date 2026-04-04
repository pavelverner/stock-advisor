@echo off
echo Spouštím Cloudflare Tunnel pro veřejný přístup...
echo Veřejná URL se zobrazí níže (funguje cca 30s po startu).
echo Sdílej tuto URL s kýmkoliv - přistoupí na tvůj dashboard.
echo.
"C:\Program Files (x86)\cloudflared\cloudflared.exe" tunnel --url http://localhost:8501
pause

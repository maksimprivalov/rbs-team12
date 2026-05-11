#!/bin/bash

# OS verzija, kernel, uptime, NTP, paketi, logging

mkdir -p /tmp/audit

echo "=============================="
echo " 1. OPERATIVNI SISTEM"
echo "=============================="
cat /etc/os-release 2>/dev/null || cat /etc/debian_version 2>/dev/null || cat /etc/redhat-release 2>/dev/null
echo ""

echo "=============================="
echo " 2. KERNEL I UPTIME"
echo "=============================="
uname -a
uptime
echo ""

echo "=============================="
echo " 3. VREMENSKA ZONA I NTP"
echo "=============================="
echo "Timezone:"
cat /etc/timezone 2>/dev/null || timedatectl 2>/dev/null

echo ""
echo "NTP proces:"
ps -edf | grep -E '[n]tp|[c]hrony|[t]imesyncd'

echo ""
echo "NTP peers:"
ntpq -p -n 2>/dev/null || echo "ntpq nije dostupan"
echo ""

echo "=============================="
echo " 4. INSTALIRANI PAKETI"
echo "=============================="
echo "Ukupno paketa:"
dpkg -l 2>/dev/null | grep "^ii" | wc -l || rpm -qa 2>/dev/null | wc -l

echo ""
echo "Potencijalno nepotrebni paketi (GUI, telnet, ftp):"
dpkg -l 2>/dev/null | grep -iE "xorg|gnome|kde|telnet|^ii.*ftp|games" || echo "Nisu pronadjeni"
echo ""

echo "=============================="
echo " 5. LOGGING"
echo "=============================="
echo "Logging proces:"
ps -edf | grep -E '[r]syslog|[s]yslogd|[s]yslog-ng'

echo ""
echo "Remote logging u rsyslog.conf:"
grep -E '^\*\.\*\s+@@?' /etc/rsyslog.conf 2>/dev/null || echo "Remote logging nije konfigurisan"

echo ""
echo "Dozvole na /var/log:"
ls -la /var/log/

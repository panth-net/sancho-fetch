#!/usr/bin/env bash
# Double-click uninstaller for macOS. Wraps uninstall.sh so non-coders can
# uninstall Sancho Fetch from Finder.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
bash ./uninstall.sh
EXITCODE=$?
echo
if [ "$EXITCODE" -eq 0 ]; then
  echo "Uninstaller finished."
else
  echo "Uninstaller exited with code $EXITCODE."
  echo "You can also open Terminal in the sancho-fetch folder and run:"
  echo "  bash installers/uninstall.sh"
fi
echo "Press Return to close this window."
read -r _
exit "$EXITCODE"

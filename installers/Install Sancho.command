#!/usr/bin/env bash
# Double-click installer for macOS. Wraps setup.sh so non-coders can
# install Sancho Fetch from Finder.
cd "$(dirname "${BASH_SOURCE[0]}")" || exit 1
bash ./setup.sh
EXITCODE=$?
echo
if [ "$EXITCODE" -eq 0 ]; then
  echo "Installer finished successfully."
else
  echo "Installer failed with exit code $EXITCODE."
  echo "You can also open Terminal in the sancho-fetch folder and run:"
  echo "  bash installers/setup.sh"
fi
echo "Press Return to close this window."
read -r _
exit "$EXITCODE"

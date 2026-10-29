#!/bin/zsh
# The text-back job (launchd, com.$USER.kit.textback): runs kit-textback watch under zsh, as Kit's
# other jobs run, so its replies go out with the same permission to use Messages as the briefs.
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
python3 "$HOME/Claude/Agents/kit/.install/shared/bin/kit-textback" watch
exit $?

#!/bin/bash
# Refresh translations after changing strings in pages.yaml or the Python code:
#   1. extract YAML strings into translatable_strings.py
#   2. rebuild locale/biglinux-welcome.pot
#   3. merge it into every locale/*.po (new strings stay empty for translators)
#   4. compile usr/share/locale/<lang>/LC_MESSAGES/biglinux-welcome.mo
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

app=usr/share/biglinux/welcome
pot=locale/biglinux-welcome.pot

python3 generate_strings.py "$app/pages.yaml" "$app/translatable_strings.py"

# Historical files first keeps the catalogs' entry order (and diffs) stable
sources=("$app/widgets.py" "$app/window.py" "$app/translatable_strings.py")
for file in "$app"/*.py; do
	[[ " ${sources[*]} " == *" $file "* ]] || sources+=("$file")
done

xgettext --language=Python --from-code=UTF-8 \
	--keyword=_ --keyword=N_ --keyword=ngettext:1,2 \
	--add-comments=TRANSLATORS --package-name=biglinux-welcome \
	-o "$pot" "${sources[@]}"

for po in locale/*.po; do
	lang=$(basename "$po" .po)
	msgmerge --quiet --no-fuzzy-matching --backup=none --update "$po" "$pot"
	msgattrib --no-obsolete -o "$po" "$po"
	mkdir -p "usr/share/locale/$lang/LC_MESSAGES"
	msgfmt --check -o "usr/share/locale/$lang/LC_MESSAGES/biglinux-welcome.mo" "$po"
	printf '%-6s ' "$lang"
	LC_ALL=C msgfmt --statistics -o /dev/null "$po"
done

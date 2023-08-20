find warecorder/ -type f \( -name '*.py' -or -name '*.kv' \)  -print > __translatable_files
xgettext --from-code=UTF-8 --files-from=__translatable_files -Lpython -o warecorder/locale/_messages.pot
msgmerge --update --backup=off warecorder/locale/fr/LC_MESSAGES/witnessangel.po warecorder/locale/_messages.pot
msgfmt -c -o warecorder/locale/fr/LC_MESSAGES/witnessangel.mo warecorder/locale/fr/LC_MESSAGES/witnessangel.po
rm __translatable_files


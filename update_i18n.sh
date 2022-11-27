find src/warecorder/ -type f \( -name '*.py' -or -name '*.kv' \)  -print > __translatable_files
xgettext --from-code=UTF-8 --files-from=__translatable_files -Lpython -o src/warecorder/locale/_messages.pot
msgmerge --update --backup=off src/warecorder/locale/fr/LC_MESSAGES/witnessangel.po src/warecorder/locale/_messages.pot
msgfmt -c -o src/warecorder/locale/fr/LC_MESSAGES/witnessangel.mo src/warecorder/locale/fr/LC_MESSAGES/witnessangel.po
rm __translatable_files


find src/wanvr/ -type f \( -name '*.py' -or -name '*.kv' \)  -print > __translatable_files
xgettext --from-code=UTF-8 --files-from=__translatable_files -Lpython -o src/wanvr/locale/_messages.pot
msgmerge --update --backup=off src/wanvr/locale/fr/LC_MESSAGES/witnessangel.po src/wanvr/locale/_messages.pot
msgfmt -c -o src/wanvr/locale/fr/LC_MESSAGES/witnessangel.mo src/wanvr/locale/fr/LC_MESSAGES/witnessangel.po



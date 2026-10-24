import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.0-alpha.1/docs/CHANGELOG.md'

/**
 * 2.0.0-alpha.1:0, 2.0's first pre-release (B10a; the owner's decision 28 on
 * #251: alphas, then betas), sideloaded from its GitHub pre-release, never
 * on Start9's registries. 1.2.10:0's migration was empty, so it is bumped in
 * place (Start9's versions.md), with no migration of its own: the app
 * migrates its database itself.
 */
export const current = VersionInfo.of({
  version: '2.0.0-alpha.1:0',
  releaseNotes: {
    en_US: `**This is BitcoinTX 2.0's first alpha: a pre-release for trying 2.0 before it's released. Don't keep your real records in it.** Nobody gets it as an update: you sideload it yourself, it may have bugs, and Start9's store stays on BitcoinTX 1.x.

**Before you sideload it**

- **Make a StartOS backup of BitcoinTX, and keep it**: it's your way back to 1.x. A later backup of BitcoinTX to the same drive replaces it, so back the alpha up to another drive.
- **Download BitcoinTX's own backup too** (Settings, Backup & Restore).
- **Coming from 1.2.9?** The alpha has every 1.x fix up to 1.2.10. Read [1.2.10's notes](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) first: four of its fixes can change a tax figure, each with what to do.

**Going back to 1.x**

Uninstall BitcoinTX (which deletes the alpha's data, the copy below included) and restore the StartOS backup you made before: it brings back 1.x with its records. Without it, sideload 1.x from its GitHub release and restore, in its Settings, the BitcoinTX backup you downloaded under 1.x. What you entered in the alpha can't go back: 1.x can't read a 2.0 database or backup. While a server runs an alpha or a beta, StartOS offers it no 1.x update: fixes come in the next pre-release.

**After updating**

- **Update your AI connector**: in your AI app's configuration, change the version after btctx-mcp== to 2.0.0a1 and restart the AI app. Once your ledger has a second wallet or exchange, an older connector can still read it, but BitcoinTX refuses its changes. A ledger with an extra bitcoin account made through 1.x's account API has two wallets as soon as it's updated.
- **Reload BitcoinTX's page** in your browser.
- **Your figures don't change**, except a very old ledger's rows (below). Every transaction keeps its account: your bank, wallet and exchange are 2.0's first bank, wallet and exchange. Before the update BitcoinTX keeps a copy of your 1.x database, backups/btctx-pre-2.0-….db, so its data takes about twice its space, once; it never deletes that copy.

**What's new in 2.0**

- **Each wallet, exchange and bank you use**, added in Settings (Wallets, exchanges and banks), each wallet and exchange with its own coins. From 2025, cost basis is figured wallet by wallet and account by account; unless you identify the coins you sell, first in, first out within each, by the date first acquired (Treas. Reg. §1.1012-1(j)).
- **Form 8949 and the tax report per exchange**, with each exchange's own Form 1099-DA setting.
- **An importer for any exchange's CSV file**, with ready-made mappings.
- **A change that would move an earlier tax year's figures asks first.**
- **A ledger started before 0.9.2**: a transaction saved then into an account made through BitcoinTX's old account API now counts by that account's currency, so its income, rebates and gifts can move, and once the ledger is recalculated a spend's network fee from it lowers the spend's proceeds and gain. Ledger Review lists these rows ("Transactions in an account made through BitcoinTX's old account API"): check each, then run Recalculate Ledger.

[Everything in 2.0.0-alpha.1](${CHANGELOG})`,
    es_ES: `**Esta es la primera alfa de BitcoinTX 2.0: una versión preliminar para probar la 2.0 antes de su lanzamiento. No guardes en ella tus registros reales.** Nadie la recibe como actualización: la instalas tú mismo con Sideload, puede tener errores, y la tienda de Start9 sigue en BitcoinTX 1.x.

**Antes de instalarla**

- **Haz una copia de seguridad de BitcoinTX en StartOS y guárdala**: es tu forma de volver a la 1.x. Una copia posterior de BitcoinTX en la misma unidad la sustituye, así que haz las copias de la alfa en otra unidad.
- **Descarga también la copia de seguridad propia de BitcoinTX** (Settings, Backup & Restore).
- **¿Vienes de la 1.2.9?** La alfa trae todas las correcciones de la 1.x hasta la 1.2.10. Lee antes [las notas de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cuatro de sus correcciones pueden cambiar una cifra fiscal, cada una con lo que hay que hacer.

**Volver a la 1.x**

Desinstala BitcoinTX (lo que borra los datos de la alfa, incluida la copia de abajo) y restaura la copia de seguridad de StartOS que hiciste antes: vuelve la 1.x con sus registros. Sin ella, instala la 1.x desde su versión en GitHub con Sideload y restaura, en su Settings, la copia de BitcoinTX que descargaste con la 1.x. Lo que hayas introducido en la alfa no puede volver: la 1.x no puede leer una base de datos ni una copia de la 2.0. Mientras un servidor tenga una alfa o una beta, StartOS no le ofrece actualizaciones de la 1.x: las correcciones llegan en la siguiente versión preliminar.

**Después de actualizar**

- **Actualiza tu conector de IA**: en la configuración de tu aplicación de IA, cambia la versión que sigue a btctx-mcp== por 2.0.0a1 y reinicia la aplicación de IA. Cuando tu libro contable tenga un segundo monedero o exchange, un conector anterior aún puede leerlo, pero BitcoinTX rechaza sus cambios. Un libro contable con una cuenta de bitcoin adicional creada mediante la API de cuentas de la 1.x tiene dos monederos en cuanto se actualiza.
- **Vuelve a cargar la página de BitcoinTX** en tu navegador.
- **Tus cifras no cambian**, salvo las filas de un libro contable muy antiguo (abajo). Cada transacción conserva su cuenta: tu banco, tu monedero y tu exchange son el primer banco, monedero y exchange de la 2.0. Antes de actualizar, BitcoinTX guarda una copia de tu base de datos de la 1.x, backups/btctx-pre-2.0-….db, así que sus datos ocupan una vez el doble de espacio; nunca borra esa copia.

**Novedades de la 2.0**

- **Cada monedero, exchange y banco que uses**, añadidos en Settings (Wallets, exchanges and banks), cada monedero y cada exchange con sus propias monedas. A partir de 2025, el coste base se calcula monedero por monedero y cuenta por cuenta; salvo que identifiques las monedas que vendes, se aplica la regla de primero en entrar, primero en salir dentro de cada uno, según la fecha en que se adquirieron por primera vez (Treas. Reg. §1.1012-1(j)).
- **El formulario 8949 y el informe fiscal por exchange**, con el ajuste del formulario 1099-DA de cada exchange.
- **Un importador para el archivo CSV de cualquier exchange**, con correspondencias ya hechas.
- **Un cambio que movería las cifras de un año fiscal anterior pregunta antes.**
- **Un libro contable empezado antes de la 0.9.2**: una transacción guardada entonces en una cuenta creada con la antigua API de cuentas de BitcoinTX ahora se cuenta según la moneda de esa cuenta, así que sus ingresos, reembolsos y regalos pueden moverse, y, una vez recalculado el libro contable, la comisión de red de un gasto en ella reduce los ingresos y la ganancia de ese gasto. Ledger Review muestra estas filas ("Transactions in an account made through BitcoinTX's old account API"): revisa cada una y después ejecuta Recalculate Ledger.

[Todo lo de la 2.0.0-alpha.1](${CHANGELOG})`,
    de_DE: `**Dies ist die erste Alpha von BitcoinTX 2.0: eine Vorabversion, um 2.0 vor der Veröffentlichung auszuprobieren. Bewahre darin nicht deine echten Daten auf.** Niemand bekommt sie als Update: Du installierst sie selbst per Sideload, sie kann Fehler haben, und Start9s Store bleibt bei BitcoinTX 1.x.

**Bevor du sie installierst**

- **Erstelle eine StartOS-Sicherung von BitcoinTX und bewahre sie auf**: Sie ist dein Weg zurück zu 1.x. Eine spätere Sicherung von BitcoinTX auf dasselbe Laufwerk ersetzt sie, sichere die Alpha also auf ein anderes Laufwerk.
- **Lade auch die eigene Sicherung von BitcoinTX herunter** (Settings, Backup & Restore).
- **Du kommst von 1.2.9?** Die Alpha enthält jede 1.x-Korrektur bis 1.2.10. Lies zuerst [die Hinweise zu 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): Vier ihrer Korrekturen können eine Steuerzahl ändern, jede mit dem, was zu tun ist.

**Zurück zu 1.x**

Deinstalliere BitcoinTX (das löscht die Daten der Alpha, die Kopie unten eingeschlossen) und stelle die StartOS-Sicherung wieder her, die du vorher erstellt hast: Sie bringt 1.x mit seinen Daten zurück. Ohne sie installiere 1.x aus seinem GitHub-Release per Sideload und stelle in seinen Settings die BitcoinTX-Sicherung wieder her, die du unter 1.x heruntergeladen hast. Was du in der Alpha eingegeben hast, kann nicht zurück: 1.x kann keine Datenbank und keine Sicherung von 2.0 lesen. Solange ein Server eine Alpha oder Beta ausführt, bietet StartOS ihm kein 1.x-Update an: Korrekturen kommen in der nächsten Vorabversion.

**Nach dem Update**

- **Aktualisiere deinen KI-Connector**: Ändere in der Konfiguration deiner KI-App die Version nach btctx-mcp== in 2.0.0a1 und starte die KI-App neu. Sobald dein Journal eine zweite Wallet oder Börse hat, kann ein älterer Connector es noch lesen, aber BitcoinTX lehnt seine Änderungen ab. Ein Journal mit einem zusätzlichen Bitcoin-Konto, das über die Konten-API von 1.x angelegt wurde, hat gleich nach dem Update zwei Wallets.
- **Lade die Seite von BitcoinTX** in deinem Browser neu.
- **Deine Zahlen ändern sich nicht**, außer bei den Zeilen eines sehr alten Journals (unten). Jede Transaktion behält ihr Konto: Deine Bank, deine Wallet und deine Börse sind die erste Bank, Wallet und Börse von 2.0. Vor dem Update legt BitcoinTX eine Kopie deiner 1.x-Datenbank an, backups/btctx-pre-2.0-….db, seine Daten brauchen also einmal etwa doppelt so viel Platz; diese Kopie löscht BitcoinTX nie.

**Neu in 2.0**

- **Jede Wallet, Börse und Bank, die du nutzt**, angelegt in Settings (Wallets, exchanges and banks), jede Wallet und jede Börse mit ihren eigenen Coins. Ab 2025 werden die Anschaffungskosten Wallet für Wallet und Konto für Konto ermittelt; sofern du die Coins, die du verkaufst, nicht identifizierst, gilt innerhalb jeder Wallet und jedes Kontos das First-in-first-out-Prinzip, nach dem Datum der ersten Anschaffung (Treas. Reg. §1.1012-1(j)).
- **Formular 8949 und der Steuerbericht pro Börse**, mit der eigenen Einstellung jeder Börse zum Formular 1099-DA.
- **Ein Import für die CSV-Datei jeder Börse**, mit fertigen Zuordnungen.
- **Eine Änderung, die die Zahlen eines früheren Steuerjahres verschieben würde, fragt vorher.**
- **Ein Journal, das vor 0.9.2 begonnen wurde**: Eine Transaktion, die damals in einem über die alte Konten-API von BitcoinTX angelegten Konto gespeichert wurde, zählt jetzt nach der Währung dieses Kontos. Ihre Einkünfte, Rückvergütungen und Geschenke können sich dadurch verschieben, und nach einer Neuberechnung des Journals senkt die Netzwerkgebühr einer Ausgabe daraus deren Erlös und Gewinn. Ledger Review listet diese Zeilen auf ("Transactions in an account made through BitcoinTX's old account API"): Prüfe jede, dann führe Recalculate Ledger aus.

[Alles in 2.0.0-alpha.1](${CHANGELOG})`,
    pl_PL: `**To pierwsza alfa BitcoinTX 2.0: wersja wstępna do wypróbowania 2.0 przed jej wydaniem. Nie trzymaj w niej swoich prawdziwych danych.** Nikt nie dostaje jej jako aktualizacji: instalujesz ją sam przez Sideload, może zawierać błędy, a sklep Start9 pozostaje przy BitcoinTX 1.x.

**Zanim ją zainstalujesz**

- **Zrób kopię zapasową BitcoinTX w StartOS i zachowaj ją**: to Twoja droga powrotu do 1.x. Późniejsza kopia BitcoinTX na tym samym dysku ją zastępuje, więc kopie alfy rób na innym dysku.
- **Pobierz też własną kopię zapasową BitcoinTX** (Settings, Backup & Restore).
- **Przechodzisz z 1.2.9?** Alfa zawiera wszystkie poprawki 1.x do wersji 1.2.10. Najpierw przeczytaj [informacje o 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cztery z jej poprawek mogą zmienić wynik podatkowy, każda z opisem, co zrobić.

**Powrót do 1.x**

Odinstaluj BitcoinTX (co usuwa dane alfy, łącznie z kopią opisaną niżej) i przywróć kopię zapasową StartOS zrobioną wcześniej: wraca 1.x z jej danymi. Bez niej zainstaluj 1.x z jej wydania na GitHubie przez Sideload i przywróć w jej Settings kopię BitcoinTX pobraną w 1.x. Tego, co wprowadzisz w alfie, nie da się przenieść z powrotem: 1.x nie odczyta bazy danych ani kopii zapasowej z 2.0. Dopóki serwer ma alfę lub betę, StartOS nie proponuje mu aktualizacji 1.x: poprawki przychodzą w kolejnej wersji wstępnej.

**Po aktualizacji**

- **Zaktualizuj łącznik AI**: w konfiguracji aplikacji AI zmień wersję po btctx-mcp== na 2.0.0a1 i uruchom aplikację AI ponownie. Gdy Twoja księga ma drugi portfel lub drugą giełdę, starszy łącznik nadal może ją czytać, ale BitcoinTX odrzuca jego zmiany. Księga z dodatkowym kontem bitcoinowym utworzonym przez API kont 1.x ma dwa portfele od razu po aktualizacji.
- **Odśwież stronę BitcoinTX** w przeglądarce.
- **Twoje wyniki się nie zmieniają**, z wyjątkiem wierszy bardzo starej księgi (niżej). Każda transakcja zachowuje swoje konto: Twój bank, portfel i giełda to pierwszy bank, portfel i giełda w 2.0. Przed aktualizacją BitcoinTX zachowuje kopię bazy danych 1.x, backups/btctx-pre-2.0-….db, więc jednorazowo jego dane zajmują mniej więcej dwa razy więcej miejsca; tej kopii nigdy nie usuwa.

**Nowości w 2.0**

- **Każdy portfel, giełda i bank, których używasz**, dodane w Settings (Wallets, exchanges and banks), każdy portfel i każda giełda z własnymi monetami. Od 2025 r. koszt nabycia ustala się osobno dla każdego portfela i każdego konta; o ile nie wskażesz, które monety sprzedajesz, w obrębie każdego z nich obowiązuje zasada „pierwsze weszło, pierwsze wyszło” według daty pierwszego nabycia (Treas. Reg. §1.1012-1(j)).
- **Formularz 8949 i raport podatkowy dla każdej giełdy**, z własnym ustawieniem formularza 1099-DA każdej giełdy.
- **Import pliku CSV z dowolnej giełdy**, z gotowymi dopasowaniami.
- **Zmiana, która przesunęłaby wyniki wcześniejszego roku podatkowego, najpierw pyta.**
- **Księga założona przed 0.9.2**: transakcja zapisana wtedy na koncie utworzonym przez dawne API kont BitcoinTX liczy się teraz według waluty tego konta, więc jej przychody, zwroty i darowizny mogą się zmienić, a po przeliczeniu księgi opłata sieciowa wydatku z tego konta obniża przychód i zysk z tego wydatku. Ledger Review wymienia te wiersze ("Transactions in an account made through BitcoinTX's old account API"): sprawdź każdy, a potem uruchom Recalculate Ledger.

[Wszystko w 2.0.0-alpha.1](${CHANGELOG})`,
    fr_FR: `**Voici la première alpha de BitcoinTX 2.0 : une préversion pour essayer la 2.0 avant sa sortie. N’y gardez pas vos vrais registres.** Personne ne la reçoit en mise à jour : vous l’installez vous-même par Sideload, elle peut contenir des bugs, et la boutique de Start9 reste sur BitcoinTX 1.x.

**Avant de l’installer**

- **Faites une sauvegarde StartOS de BitcoinTX, et gardez-la** : c’est votre chemin de retour vers la 1.x. Une sauvegarde ultérieure de BitcoinTX sur le même disque la remplace : sauvegardez donc l’alpha sur un autre disque.
- **Téléchargez aussi la sauvegarde propre à BitcoinTX** (Settings, Backup & Restore).
- **Vous venez de la 1.2.9 ?** L’alpha contient toutes les corrections de la 1.x jusqu’à la 1.2.10. Lisez d’abord [les notes de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) : quatre de ses corrections peuvent changer un chiffre fiscal, chacune avec ce qu’il faut faire.

**Revenir à la 1.x**

Désinstallez BitcoinTX (ce qui efface les données de l’alpha, y compris la copie ci-dessous) et restaurez la sauvegarde StartOS faite avant : elle ramène la 1.x avec ses registres. Sans elle, installez la 1.x depuis sa version GitHub par Sideload et restaurez, dans ses Settings, la sauvegarde BitcoinTX téléchargée sous la 1.x. Ce que vous avez saisi dans l’alpha ne peut pas revenir : la 1.x ne lit ni une base de données ni une sauvegarde de la 2.0. Tant qu’un serveur fait tourner une alpha ou une bêta, StartOS ne lui propose aucune mise à jour 1.x : les corrections arrivent dans la préversion suivante.

**Après la mise à jour**

- **Mettez à jour votre connecteur IA** : dans la configuration de votre application d’IA, remplacez la version après btctx-mcp== par 2.0.0a1 et redémarrez l’application d’IA. Dès que votre registre a un deuxième portefeuille ou une deuxième plateforme, un connecteur plus ancien peut encore le lire, mais BitcoinTX refuse ses modifications. Un registre avec un compte bitcoin supplémentaire créé via l’API des comptes de la 1.x a deux portefeuilles dès la mise à jour.
- **Rechargez la page de BitcoinTX** dans votre navigateur.
- **Vos chiffres ne changent pas**, sauf les lignes d’un registre très ancien (ci-dessous). Chaque transaction garde son compte : votre banque, votre portefeuille et votre plateforme sont la première banque, le premier portefeuille et la première plateforme de la 2.0. Avant la mise à jour, BitcoinTX garde une copie de votre base de données 1.x, backups/btctx-pre-2.0-….db : ses données prennent donc une fois environ deux fois plus de place ; BitcoinTX ne supprime jamais cette copie.

**Nouveautés de la 2.0**

- **Chaque portefeuille, plateforme et banque que vous utilisez**, ajoutés dans Settings (Wallets, exchanges and banks), chaque portefeuille et chaque plateforme avec ses propres bitcoins. À partir de 2025, le coût d’acquisition se calcule portefeuille par portefeuille et compte par compte ; sauf si vous identifiez les bitcoins que vous vendez, la règle du premier entré, premier sorti s’applique au sein de chacun, selon la date de première acquisition (Treas. Reg. §1.1012-1(j)).
- **Le formulaire 8949 et le rapport fiscal par plateforme**, avec le réglage du formulaire 1099-DA propre à chaque plateforme.
- **Un import pour le fichier CSV de n’importe quelle plateforme**, avec des correspondances toutes prêtes.
- **Une modification qui déplacerait les chiffres d’une année fiscale antérieure demande d’abord.**
- **Un registre commencé avant la 0.9.2** : une transaction enregistrée alors dans un compte créé par l’ancienne API des comptes de BitcoinTX compte désormais selon la devise de ce compte : ses revenus, remboursements et dons reçus peuvent bouger, et une fois le registre recalculé, les frais de réseau d’une dépense qui en vient réduisent le produit et le gain de cette dépense. Ledger Review liste ces lignes ("Transactions in an account made through BitcoinTX's old account API") : vérifiez chacune, puis lancez Recalculate Ledger.

[Tout ce que contient la 2.0.0-alpha.1](${CHANGELOG})`,
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})

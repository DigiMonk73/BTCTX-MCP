import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.0-alpha.3/docs/CHANGELOG.md'

const ALPHA_1 =
  'https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0-alpha.1'

/**
 * 2.0.0-alpha.3:0, 2.0's third pre-release (B10a; the owner's decision 28
 * on #251: alphas, then betas), sideloaded from its GitHub pre-release, never
 * on Start9's registries. 2.0.0-alpha.2:0's migration was empty, so it is
 * bumped in place (Start9's versions.md), with no migration of its own: the
 * app migrates its database itself (0101, coin choice). Its notes say what's
 * new since alpha.2, and keep, for a tester coming straight from 1.x, the
 * backup first and the way back.
 */
export const current = VersionInfo.of({
  version: '2.0.0-alpha.3:0',
  releaseNotes: {
    en_US: `**This is BitcoinTX 2.0's third alpha: a pre-release for trying 2.0 before it's released. Don't keep your real records in it.** Nobody gets it as an update: you sideload it yourself, it may have bugs, and Start9's store stays on BitcoinTX 1.x.

**New since 2.0.0-alpha.2**

- **Choose which coins leave a wallet.** On a Spent, Gift, Donation or Lost withdrawal from one of your wallets, or a Transfer out of one, **Choose which coins leave** lists each purchase or deposit the wallet holds, and you say how much bitcoin leaves from each. Choose coins only if you decided which ones to send by the time they left, and your records show it; otherwise the oldest coins leave (Treas. Reg. §1.1012-1(j)). Exchanges stay oldest first. An edit, Recalculate Ledger, a backup and a CSV export and import keep the coins you chose, and the Complete Tax Report lists them. Some other texts (the disclaimer, the Complete Tax Report's Using these forms) still say the oldest coins always leave: a later alpha updates them.
- **Each wallet's and exchange's own cost**: with more than one wallet or exchange, opening Wallet (BTC) or Exchange (BTC) in Portfolio Overview shows what each account's bitcoin cost and, with a price, its unrealized gain or loss.
- **Fixes**, among them: an exchange's file finds the trades you recorded in another exchange before 2.0; adding an exchange asks whether it sends a Form 1099-DA; a restore keeps your saved exchange-file mappings; an account's name prints in the tax report (one that prints as "?" can be renamed in Settings); a consolidation stays one when you change its From Account; Connect an AI Assistant names a pre-release's connector apart from your BitcoinTX's.
- **If you tested alpha.1 or alpha.2**: if your AI app's \`bitcointx\` entry reached another BitcoinTX (the Mac app, another server) and you replaced it with the configuration of StartOS's Connect an AI Assistant, set it back; the action now names this one \`bitcointx-preview\`. A Transfer you meant as a consolidation shows as "Consolidation" in the Transactions list; one listed between two different accounts moved coins, and can be edited back.
- **Update your AI connector**: in your AI app's configuration, change the version after btctx-mcp== to 2.0.0a3, then restart the AI app. It records the coins you choose.
- **Reload BitcoinTX's page** in your browser to see them.

Updating from alpha.2 changes no figure. It adds coin choice to the database, after copying the database into backups/, as every update does. StartOS won't install an earlier alpha over it; the StartOS backup you made under 1.x still takes it back to 1.x (below).

**Coming from 1.x**

- **Before you sideload it, make a StartOS backup of BitcoinTX, and keep it**: it's your way back to 1.x. A later backup of BitcoinTX to the same drive replaces it, so back the alpha up to another drive. **Download BitcoinTX's own backup too** (Settings, Backup & Restore).
- **Coming from 1.2.9?** The alpha has every 1.x fix up to 1.2.10. Read [1.2.10's notes](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) first: four of its fixes can change a tax figure, each with what to do.
- **After updating**, reload BitcoinTX's page and update your AI connector (above): once your ledger has a second wallet or exchange, an older connector can still read it, but BitcoinTX refuses its changes, and a ledger with an extra bitcoin account made through 1.x's account API has two wallets as soon as it's updated. Every transaction keeps its account, and your figures don't change, except in a ledger started before 0.9.2: a transaction saved then into an account made through BitcoinTX's old account API now counts by that account's currency, so its income, rebates and gifts can move, and once the ledger is recalculated a spend's network fee from it lowers the spend's proceeds and gain. Ledger Review lists these rows ("Transactions in an account made through BitcoinTX's old account API"): check each, then run Recalculate Ledger. Before the update BitcoinTX keeps a copy of your 1.x database, backups/btctx-pre-2.0-….db, so BitcoinTX's data takes about twice the space (one copy, made once); it never deletes that copy.
- **What's new in 2.0**: your wallets, exchanges and banks, added in Settings (Wallets, exchanges and banks), each wallet and exchange with its own coins; Form 8949 per exchange; an importer for any exchange's CSV file; a question before an earlier tax year's figures move. [alpha.1's notes](${ALPHA_1}) say more.

**Going back to 1.x**

Uninstall BitcoinTX (which deletes the alpha's data, the copy above included) and restore the StartOS backup you made before: it brings back 1.x with its records. Without it, sideload 1.x from its GitHub release and restore, in its Settings, the BitcoinTX backup you downloaded under 1.x. What you entered in the alpha can't go back: 1.x can't read a 2.0 database or backup. While a server runs an alpha or a beta, StartOS offers it no 1.x update: fixes come in the next pre-release.

[Everything in 2.0.0-alpha.3](${CHANGELOG})`,
    es_ES: `**Esta es la tercera alfa de BitcoinTX 2.0: una versión preliminar para probar la 2.0 antes de su lanzamiento. No guardes en ella tus registros reales.** Nadie la recibe como actualización: la instalas tú mismo con Sideload, puede tener errores, y la tienda de Start9 sigue en BitcoinTX 1.x.

**Novedades desde la 2.0.0-alpha.2**

- **Elige qué monedas salen de un monedero.** En un retiro Spent, Gift, Donation o Lost desde uno de tus monederos, o en un Transfer que sale de uno, **Choose which coins leave** muestra cada compra o depósito que tiene el monedero, y tú indicas cuánto bitcoin sale de cada uno. Elige monedas solo si, a más tardar cuando salieron, ya habías decidido cuáles enviar, y tus registros lo muestran; si no, salen las más antiguas (Treas. Reg. §1.1012-1(j)). Los exchanges siguen sacando primero las más antiguas. Una edición, Recalculate Ledger, una copia de seguridad y una exportación e importación CSV conservan las monedas elegidas, y el Complete Tax Report las muestra. Algunos otros textos (el aviso legal, Using these forms del Complete Tax Report) aún dicen que siempre salen las monedas más antiguas: una alfa posterior los actualiza.
- **El coste propio de cada monedero y exchange**: con más de un monedero o exchange, al abrir Wallet (BTC) o Exchange (BTC) en Portfolio Overview se ve cuánto costó el bitcoin de cada cuenta y, con un precio, su ganancia o pérdida no realizada.
- **Correcciones**, entre ellas: el archivo de un exchange encuentra las operaciones que registraste en otro exchange antes de la 2.0; al añadir un exchange se pregunta si envía el formulario 1099-DA; una restauración conserva tus correspondencias guardadas de archivos de exchange; el nombre de una cuenta se imprime en el informe fiscal (uno que salga como "?" se puede renombrar en Settings); una consolidación sigue siéndolo al cambiar su From Account; Connect an AI Assistant distingue el conector de una versión preliminar del de tu BitcoinTX.
- **Si probaste la alpha.1 o la alpha.2**: si la entrada \`bitcointx\` de tu aplicación de IA llegaba a otro BitcoinTX (la aplicación de Mac, otro servidor) y la sustituiste por la configuración de Connect an AI Assistant de StartOS, devuélvela a como estaba; la acción ahora llama a esta \`bitcointx-preview\`. Un Transfer que querías como consolidación aparece como "Consolidation" en la lista de Transactions; uno listado entre dos cuentas distintas movió monedas, y se puede editar para deshacerlo.
- **Actualiza tu conector de IA**: en la configuración de tu aplicación de IA, cambia la versión que sigue a btctx-mcp== por 2.0.0a3 y reinicia la aplicación de IA. Registra las monedas que elijas.
- **Vuelve a cargar la página de BitcoinTX** en tu navegador para ver los cambios.

Actualizar desde la 2.0.0-alpha.2 no cambia ninguna cifra. Añade la elección de monedas a la base de datos, tras copiarla en backups/, como en cada actualización. StartOS no permite instalar encima una alfa anterior; la copia de seguridad de StartOS que hiciste con la 1.x sigue devolviéndolo a la 1.x (abajo).

**Si vienes de la 1.x**

- **Antes de instalarla, haz una copia de seguridad de BitcoinTX en StartOS y guárdala**: es tu forma de volver a la 1.x. Una copia posterior de BitcoinTX en la misma unidad la sustituye, así que haz las copias de la alfa en otra unidad. **Descarga también la copia de seguridad propia de BitcoinTX** (Settings, Backup & Restore).
- **¿Vienes de la 1.2.9?** La alfa trae todas las correcciones de la 1.x hasta la 1.2.10. Lee antes [las notas de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cuatro de sus correcciones pueden cambiar una cifra fiscal, cada una con lo que hay que hacer.
- **Después de actualizar**, vuelve a cargar la página de BitcoinTX y actualiza tu conector de IA (arriba): cuando tu libro contable tenga un segundo monedero o exchange, un conector anterior aún puede leerlo, pero BitcoinTX rechaza sus cambios, y un libro contable con una cuenta de bitcoin adicional creada mediante la API de cuentas de la 1.x tiene dos monederos en cuanto se actualiza. Cada transacción conserva su cuenta, y tus cifras no cambian, salvo en un libro contable empezado antes de la 0.9.2: una transacción guardada entonces en una cuenta creada con la antigua API de cuentas de BitcoinTX ahora se cuenta según la moneda de esa cuenta, así que sus ingresos, rebates y regalos recibidos pueden cambiar, y, una vez recalculado el libro contable, la comisión de red de un gasto desde esa cuenta reduce el importe recibido y la ganancia de ese gasto. Ledger Review muestra estas filas ("Transactions in an account made through BitcoinTX's old account API"): revisa cada una y después ejecuta Recalculate Ledger. Antes de actualizar, BitcoinTX guarda una copia de tu base de datos de la 1.x, backups/btctx-pre-2.0-….db, así que sus datos pasan a ocupar más o menos el doble (una sola copia); nunca borra esa copia.
- **Novedades de la 2.0**: tus monederos, exchanges y bancos, añadidos en Settings (Wallets, exchanges and banks), cada monedero y cada exchange con sus propias monedas; el formulario 8949 por exchange; un importador para el archivo CSV de cualquier exchange; una pregunta antes de que cambien las cifras de un año fiscal anterior. Más detalles en [las notas de la 2.0.0-alpha.1](${ALPHA_1}).

**Volver a la 1.x**

Desinstala BitcoinTX (lo que borra los datos de la alfa, incluida la copia de arriba) y restaura la copia de seguridad de StartOS que hiciste antes: vuelve la 1.x con sus registros. Sin ella, instala la 1.x desde su versión en GitHub con Sideload y restaura, en su Settings, la copia de BitcoinTX que descargaste con la 1.x. Lo que hayas introducido en la alfa no puede volver: la 1.x no puede leer una base de datos ni una copia de la 2.0. Mientras un servidor tenga una alfa o una beta, StartOS no le ofrece actualizaciones de la 1.x: las correcciones llegan en la siguiente versión preliminar.

[Todo lo de la 2.0.0-alpha.3](${CHANGELOG})`,
    de_DE: `**Dies ist die dritte Alpha von BitcoinTX 2.0: eine Vorabversion, um 2.0 vor der Veröffentlichung auszuprobieren. Bewahre darin nicht deine echten Daten auf.** Niemand bekommt sie als Update: Du installierst sie selbst per Sideload, sie kann Fehler haben, und Start9s Store bleibt bei BitcoinTX 1.x.

**Neu seit 2.0.0-alpha.2**

- **Wähle, welche Coins eine Wallet verlassen.** Bei einer Auszahlung Spent, Gift, Donation oder Lost aus einer deiner Wallets oder einem Transfer aus einer Wallet listet **Choose which coins leave** jeden Kauf und jede Einzahlung auf, die die Wallet hält, und du gibst an, wie viel Bitcoin aus jedem abgeht. Wähle Coins nur, wenn du bis zu ihrem Abgang entschieden hast, welche du sendest, und deine Unterlagen das zeigen; sonst verlassen die ältesten Coins die Wallet (Treas. Reg. §1.1012-1(j)). Börsen bleiben bei den ältesten zuerst. Eine Bearbeitung, Recalculate Ledger, eine Sicherung sowie ein CSV-Export und -Import behalten die gewählten Coins, und der Complete Tax Report listet sie auf. Einige andere Texte (der Haftungsausschluss, Using these forms im Complete Tax Report) sagen noch, dass immer die ältesten Coins gehen: Eine spätere Alpha passt sie an.
- **Die eigenen Kosten jeder Wallet und Börse**: Hast du mehr als eine Wallet oder Börse und öffnest in Portfolio Overview Wallet (BTC) oder Exchange (BTC), siehst du, was die Bitcoin jedes Kontos gekostet haben, und mit einem Preis den nicht realisierten Gewinn oder Verlust.
- **Korrekturen**, darunter: Die Datei einer Börse findet die Trades, die du vor 2.0 in einer anderen Börse erfasst hast; beim Hinzufügen einer Börse wird gefragt, ob sie ein Formular 1099-DA schickt; eine Wiederherstellung behält deine gespeicherten Zuordnungen für Börsendateien; der Name eines Kontos wird im Steuerbericht gedruckt (einen, der als "?" erscheint, kannst du in Settings umbenennen); eine Konsolidierung bleibt eine, wenn du ihr From Account änderst; Connect an AI Assistant unterscheidet den Connector einer Vorabversion von dem deines BitcoinTX.
- **Wenn du alpha.1 oder alpha.2 getestet hast**: Erreichte der Eintrag \`bitcointx\` deiner KI-App ein anderes BitcoinTX (die Mac-App, einen anderen Server) und hast du ihn durch die Konfiguration von Connect an AI Assistant aus StartOS ersetzt, stelle ihn wieder her; die Aktion nennt diesen jetzt \`bitcointx-preview\`. Ein Transfer, den du als Konsolidierung gemeint hast, erscheint in der Liste Transactions als "Consolidation"; einer zwischen zwei verschiedenen Konten hat Coins bewegt und lässt sich durch Bearbeiten zurücksetzen.
- **Aktualisiere deinen KI-Connector**: Ändere in der Konfiguration deiner KI-App die Version nach btctx-mcp== in 2.0.0a3 und starte die KI-App neu. Er erfasst die Coins, die du wählst.
- **Lade die Seite von BitcoinTX** in deinem Browser neu, um die Änderungen zu sehen.

Das Update von 2.0.0-alpha.2 ändert keine Zahl. Es ergänzt die Datenbank um die Coin-Auswahl, nachdem es sie, wie jedes Update, nach backups/ kopiert hat. StartOS installiert keine frühere Alpha wieder darüber; die StartOS-Sicherung, die du unter 1.x erstellt hast, bringt es weiterhin zu 1.x zurück (unten).

**Wenn du von 1.x kommst**

- **Erstelle vor der Installation eine StartOS-Sicherung von BitcoinTX und bewahre sie auf**: Sie ist dein Weg zurück zu 1.x. Eine spätere Sicherung von BitcoinTX auf dasselbe Laufwerk ersetzt sie, sichere die Alpha also auf ein anderes Laufwerk. **Lade auch die eigene Sicherung von BitcoinTX herunter** (Settings, Backup & Restore).
- **Du kommst von 1.2.9?** Die Alpha enthält jede 1.x-Korrektur bis 1.2.10. Lies zuerst [die Hinweise zu 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): Vier ihrer Korrekturen können eine Steuerzahl ändern, jede mit dem, was zu tun ist.
- **Nach dem Update** lade die Seite von BitcoinTX neu und aktualisiere deinen KI-Connector (oben): Sobald dein Journal eine zweite Wallet oder Börse hat, kann ein älterer Connector es noch lesen, aber BitcoinTX lehnt seine Änderungen ab, und ein Journal mit einem zusätzlichen Bitcoin-Konto, das über die Konten-API von 1.x angelegt wurde, hat gleich nach dem Update zwei Wallets. Jede Transaktion behält ihr Konto, und deine Zahlen ändern sich nicht, außer in einem Journal, das vor 0.9.2 begonnen wurde: Eine Transaktion, die damals in einem über die alte Konten-API von BitcoinTX angelegten Konto gespeichert wurde, zählt jetzt nach der Währung dieses Kontos. Deren Einkünfte, Rebates und erhaltene Geschenke können sich dadurch verschieben, und nach einer Neuberechnung des Journals senkt die Netzwerkgebühr einer Ausgabe daraus deren Erlös und Gewinn. Ledger Review listet diese Zeilen auf ("Transactions in an account made through BitcoinTX's old account API"): Prüfe jede, dann führe Recalculate Ledger aus. Vor dem Update legt BitcoinTX eine Kopie deiner 1.x-Datenbank an, backups/btctx-pre-2.0-….db, seine Daten brauchen also einmal etwa doppelt so viel Platz; diese Kopie löscht BitcoinTX nie.
- **Neu in 2.0**: deine Wallets, Börsen und Banken, angelegt in Settings (Wallets, exchanges and banks), jede Wallet und jede Börse mit ihren eigenen Coins; Formular 8949 pro Börse; ein Import für die CSV-Datei jeder Börse; eine Frage, bevor sich die Zahlen eines früheren Steuerjahres verschieben. Mehr dazu in [den Hinweisen zu 2.0.0-alpha.1](${ALPHA_1}).

**Zurück zu 1.x**

Deinstalliere BitcoinTX (das löscht die Daten der Alpha, die Kopie oben eingeschlossen) und stelle die StartOS-Sicherung wieder her, die du vorher erstellt hast: Sie bringt 1.x mit seinen Daten zurück. Ohne sie installiere 1.x aus seinem GitHub-Release per Sideload und stelle in seinen Settings die BitcoinTX-Sicherung wieder her, die du unter 1.x heruntergeladen hast. Was du in der Alpha eingegeben hast, kann nicht zurück: 1.x kann keine Datenbank und keine Sicherung von 2.0 lesen. Solange ein Server eine Alpha oder Beta ausführt, bietet StartOS ihm kein 1.x-Update an: Korrekturen kommen in der nächsten Vorabversion.

[Alles in 2.0.0-alpha.3](${CHANGELOG})`,
    pl_PL: `**To trzecia alfa BitcoinTX 2.0: wersja wstępna do wypróbowania 2.0 przed jej wydaniem. Nie trzymaj w niej swoich prawdziwych danych.** Nikt nie dostaje jej jako aktualizacji: instalujesz ją sam przez Sideload, może zawierać błędy, a sklep Start9 pozostaje przy BitcoinTX 1.x.

**Nowości od 2.0.0-alpha.2**

- **Wybierz, które monety opuszczają portfel.** Przy wypłacie Spent, Gift, Donation lub Lost z jednego z Twoich portfeli albo przy Transfer z portfela **Choose which coins leave** pokazuje każdy zakup lub wpłatę, które portfel przechowuje, a Ty podajesz, ile bitcoina wychodzi z każdego. Wybieraj monety tylko wtedy, gdy najpóźniej w chwili ich wyjścia zdecydowałeś, które wysłać, i Twoje zapisy to pokazują; w przeciwnym razie wychodzą najstarsze (Treas. Reg. §1.1012-1(j)). Giełdy nadal wydają najpierw najstarsze. Edycja, Recalculate Ledger, kopia zapasowa oraz eksport i import CSV zachowują wybrane monety, a Complete Tax Report je wymienia. Niektóre inne teksty (zastrzeżenie, Using these forms w Complete Tax Report) wciąż mówią, że zawsze wychodzą najstarsze monety: kolejna alfa je zaktualizuje.
- **Własny koszt każdego portfela i giełdy**: gdy masz więcej niż jeden portfel lub giełdę, po otwarciu Wallet (BTC) lub Exchange (BTC) w Portfolio Overview widać, ile kosztował bitcoin każdego konta, a przy dostępnej cenie także jego niezrealizowany zysk lub stratę.
- **Poprawki**, między innymi: plik giełdy znajduje transakcje zapisane przed 2.0 w innej giełdzie; przy dodawaniu giełdy pojawia się pytanie, czy wysyła formularz 1099-DA; przywracanie zachowuje zapisane dopasowania plików giełd; nazwa konta drukuje się w raporcie podatkowym (nazwę drukowaną jako "?" można zmienić w Settings); konsolidacja pozostaje konsolidacją po zmianie jej From Account; Connect an AI Assistant odróżnia łącznik wersji wstępnej od łącznika Twojego BitcoinTX.
- **Jeśli testowałeś alpha.1 lub alpha.2**: jeśli wpis \`bitcointx\` w Twojej aplikacji AI łączył się z innym BitcoinTX (aplikacją na Maca, innym serwerem) i zastąpiłeś go konfiguracją z Connect an AI Assistant w StartOS, przywróć go; akcja nazywa teraz ten wpis \`bitcointx-preview\`. Transfer pomyślany jako konsolidacja widnieje na liście Transactions jako "Consolidation"; taki, który figuruje między dwoma różnymi kontami, przeniósł monety i można go cofnąć edycją.
- **Zaktualizuj łącznik AI**: w konfiguracji aplikacji AI zmień wersję po btctx-mcp== na 2.0.0a3 i uruchom aplikację AI ponownie. Zapisuje on wybrane przez Ciebie monety.
- **Odśwież stronę BitcoinTX** w przeglądarce, aby zobaczyć zmiany.

Aktualizacja z 2.0.0-alpha.2 nie zmienia żadnego wyniku. Dodaje do bazy danych wybór monet, wcześniej kopiując bazę do backups/, jak każda aktualizacja. StartOS nie pozwoli zainstalować z powrotem wcześniejszej alfy; kopia zapasowa StartOS zrobiona w 1.x nadal przywraca 1.x (niżej).

**Jeśli przechodzisz z 1.x**

- **Przed instalacją zrób kopię zapasową BitcoinTX w StartOS i zachowaj ją**: to Twoja droga powrotu do 1.x. Późniejsza kopia BitcoinTX na tym samym dysku ją zastępuje, więc kopie alfy rób na innym dysku. **Pobierz też własną kopię zapasową BitcoinTX** (Settings, Backup & Restore).
- **Przechodzisz z 1.2.9?** Alfa zawiera wszystkie poprawki 1.x do wersji 1.2.10. Najpierw przeczytaj [informacje o 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cztery z jej poprawek mogą zmienić wynik podatkowy, każda z opisem, co zrobić.
- **Po aktualizacji** odśwież stronę BitcoinTX i zaktualizuj łącznik AI (wyżej): gdy Twoja księga ma drugi portfel lub drugą giełdę, starszy łącznik nadal może ją czytać, ale BitcoinTX odrzuca jego zmiany, a księga z dodatkowym kontem bitcoinowym utworzonym przez API kont 1.x ma dwa portfele od razu po aktualizacji. Każda transakcja zachowuje swoje konto, a Twoje wyniki się nie zmieniają, z wyjątkiem księgi założonej przed 0.9.2: transakcja zapisana wtedy na koncie utworzonym przez dawne API kont BitcoinTX liczy się teraz według waluty tego konta, więc dochody, rebate i otrzymane prezenty z tego konta mogą się zmienić, a po przeliczeniu księgi opłata sieciowa wydatku z tego konta obniża przychód i zysk z tego wydatku. Ledger Review wymienia te wiersze ("Transactions in an account made through BitcoinTX's old account API"): sprawdź każdy, a potem uruchom Recalculate Ledger. Przed aktualizacją BitcoinTX zachowuje kopię bazy danych 1.x, backups/btctx-pre-2.0-….db, więc jednorazowo jego dane zajmują mniej więcej dwa razy więcej miejsca; tej kopii nigdy nie usuwa.
- **Nowości w 2.0**: Twoje portfele, giełdy i banki, dodane w Settings (Wallets, exchanges and banks), każdy portfel i każda giełda z własnymi monetami; formularz 8949 dla każdej giełdy; import pliku CSV z dowolnej giełdy; pytanie, zanim zmienią się wyniki wcześniejszego roku podatkowego. Więcej w [informacjach o 2.0.0-alpha.1](${ALPHA_1}).

**Powrót do 1.x**

Odinstaluj BitcoinTX (co usuwa dane alfy, łącznie z kopią opisaną wyżej) i przywróć kopię zapasową StartOS zrobioną wcześniej: wraca 1.x z jej danymi. Bez niej zainstaluj 1.x z jej wydania na GitHubie przez Sideload i przywróć w jej Settings kopię BitcoinTX pobraną w 1.x. Tego, co wprowadzisz w alfie, nie da się przenieść z powrotem: 1.x nie odczyta bazy danych ani kopii zapasowej z 2.0. Dopóki serwer ma alfę lub betę, StartOS nie proponuje mu aktualizacji 1.x: poprawki przychodzą w kolejnej wersji wstępnej.

[Wszystko w 2.0.0-alpha.3](${CHANGELOG})`,
    fr_FR: `**Voici la troisième alpha de BitcoinTX 2.0 : une préversion pour essayer la 2.0 avant sa sortie. N’y gardez pas vos vrais registres.** Personne ne la reçoit en mise à jour : vous l’installez vous-même par Sideload, elle peut contenir des bugs, et la boutique de Start9 reste sur BitcoinTX 1.x.

**Nouveautés depuis la 2.0.0-alpha.2**

- **Choisissez quels bitcoins quittent un portefeuille.** Sur un retrait Spent, Gift, Donation ou Lost depuis l’un de vos portefeuilles, ou un Transfer qui en sort, **Choose which coins leave** liste chaque achat ou dépôt que contient le portefeuille, et vous indiquez combien de bitcoins sortent de chacun. Ne choisissez des bitcoins que si, au moment de leur départ, vous aviez déjà décidé lesquels envoyer, et que vos registres le montrent ; sinon, les plus anciens partent (Treas. Reg. §1.1012-1(j)). Les plateformes restent au premier entré, premier sorti. Une modification, Recalculate Ledger, une sauvegarde ainsi qu’un export et un import CSV gardent les bitcoins choisis, et le Complete Tax Report les liste. Certains autres textes (l’avertissement, Using these forms du Complete Tax Report) disent encore que les plus anciens partent toujours : une alpha ultérieure les mettra à jour.
- **Le coût propre à chaque portefeuille et plateforme** : avec plus d’un portefeuille ou d’une plateforme, ouvrir Wallet (BTC) ou Exchange (BTC) dans Portfolio Overview montre ce qu’ont coûté les bitcoins de chaque compte et, avec un prix, son gain ou sa perte latents.
- **Des corrections**, entre autres : le fichier d’une plateforme retrouve les opérations enregistrées dans une autre plateforme avant la 2.0 ; l’ajout d’une plateforme demande si elle envoie un formulaire 1099-DA ; une restauration garde vos correspondances de fichiers de plateforme enregistrées ; le nom d’un compte s’imprime dans le rapport fiscal (un nom imprimé en "?" peut être renommé dans Settings) ; une consolidation en reste une quand vous changez son From Account ; Connect an AI Assistant distingue le connecteur d’une préversion de celui de votre BitcoinTX.
- **Si vous avez testé l’alpha.1 ou l’alpha.2** : si l’entrée \`bitcointx\` de votre application d’IA joignait un autre BitcoinTX (l’app Mac, un autre serveur) et que vous l’avez remplacée par la configuration de Connect an AI Assistant de StartOS, rétablissez-la ; l’action nomme désormais celle-ci \`bitcointx-preview\`. Un Transfer voulu comme consolidation apparaît comme "Consolidation" dans la liste Transactions ; un Transfer listé entre deux comptes différents a déplacé des bitcoins et peut être corrigé par une modification.
- **Mettez à jour votre connecteur IA** : dans la configuration de votre application d’IA, remplacez la version après btctx-mcp== par 2.0.0a3 et redémarrez l’application d’IA. Il enregistre les bitcoins que vous choisissez.
- **Rechargez la page de BitcoinTX** dans votre navigateur pour voir ces changements.

La mise à jour depuis la 2.0.0-alpha.2 ne change aucun chiffre. Elle ajoute le choix des bitcoins à la base de données, après l’avoir copiée dans backups/, comme chaque mise à jour. StartOS ne réinstalle pas une alpha antérieure par-dessus ; la sauvegarde StartOS faite sous la 1.x le ramène toujours à la 1.x (ci-dessous).

**Si vous venez de la 1.x**

- **Avant de l’installer, faites une sauvegarde StartOS de BitcoinTX, et gardez-la** : c’est votre chemin de retour vers la 1.x. Une sauvegarde ultérieure de BitcoinTX sur le même disque la remplace : sauvegardez donc l’alpha sur un autre disque. **Téléchargez aussi la sauvegarde propre à BitcoinTX** (Settings, Backup & Restore).
- **Vous venez de la 1.2.9 ?** L’alpha contient toutes les corrections de la 1.x jusqu’à la 1.2.10. Lisez d’abord [les notes de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) : quatre de ses corrections peuvent changer un chiffre fiscal, chacune avec ce qu’il faut faire.
- **Après la mise à jour**, rechargez la page de BitcoinTX et mettez à jour votre connecteur IA (ci-dessus) : dès que votre registre a un deuxième portefeuille ou une deuxième plateforme, un connecteur plus ancien peut encore le lire, mais BitcoinTX refuse ses modifications, et un registre avec un compte bitcoin supplémentaire créé via l’API des comptes de la 1.x a deux portefeuilles dès la mise à jour. Chaque transaction garde son compte, et vos chiffres ne changent pas, sauf dans un registre commencé avant la 0.9.2 : une transaction enregistrée alors dans un compte créé par l’ancienne API des comptes de BitcoinTX compte désormais selon la devise de ce compte ; ses revenus, rebates et dons reçus peuvent changer, et une fois le registre recalculé, les frais de réseau d’une dépense faite depuis ce compte réduisent le produit et le gain de cette dépense. Ledger Review liste ces lignes ("Transactions in an account made through BitcoinTX's old account API") : vérifiez chacune, puis lancez Recalculate Ledger. Avant la mise à jour, BitcoinTX garde une copie de votre base de données 1.x, backups/btctx-pre-2.0-….db : ses données prennent donc environ deux fois plus de place (une seule copie) ; BitcoinTX ne supprime jamais cette copie.
- **Nouveautés de la 2.0** : vos portefeuilles, plateformes et banques, ajoutés dans Settings (Wallets, exchanges and banks), chaque portefeuille et chaque plateforme avec ses propres bitcoins ; le formulaire 8949 par plateforme ; un import pour le fichier CSV de n’importe quelle plateforme ; une question avant que les chiffres d’une année fiscale antérieure ne bougent. [Les notes de la 2.0.0-alpha.1](${ALPHA_1}) en disent plus.

**Revenir à la 1.x**

Désinstallez BitcoinTX (ce qui efface les données de l’alpha, y compris la copie ci-dessus) et restaurez la sauvegarde StartOS faite avant : elle ramène la 1.x avec ses registres. Sans elle, installez la 1.x depuis sa version GitHub par Sideload et restaurez, dans ses Settings, la sauvegarde BitcoinTX téléchargée sous la 1.x. Ce que vous avez saisi dans l’alpha ne peut pas revenir : la 1.x ne lit ni une base de données ni une sauvegarde de la 2.0. Tant qu’un serveur fait tourner une alpha ou une bêta, StartOS ne lui propose aucune mise à jour 1.x : les corrections arrivent dans la préversion suivante.

[Tout ce que contient la 2.0.0-alpha.3](${CHANGELOG})`,
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})

import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.0-beta.1/docs/CHANGELOG.md'

const ALPHA_1 =
  'https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0-alpha.1'

/**
 * 2.0.0-beta.1:0, 2.0's first beta (B10a; the owner's decision 28 on #251:
 * alphas, then betas), sideloaded from its GitHub pre-release, never on
 * Start9's registries. 2.0.0-alpha.3:0's migration was empty, so it is
 * bumped in place (Start9's versions.md), with no migration of its own: the
 * app migrates its database itself. Its notes say what a beta is and what's
 * new since alpha.3, and keep, for a tester coming straight from 1.x, the
 * backup first and the way back.
 */
export const current = VersionInfo.of({
  version: '2.0.0-beta.1:0',
  releaseNotes: {
    en_US: `**This is BitcoinTX 2.0's first beta: a pre-release for trying 2.0 before it's released. Don't keep your real records in it.** A beta follows the alphas: all of 2.0 is in it, tested as a whole. It's still a pre-release on GitHub: nobody gets it as an update, you sideload it yourself, it may have bugs, and Start9's store stays on BitcoinTX 1.x, the version to use for your records.

**New since 2.0.0-alpha.3**

- **The words say what 2.0 does.** Cost basis is per-wallet FIFO: each wallet and exchange uses its own oldest coins first, and in a self-custody wallet you can choose which coins leave, if you chose them when they left. The README, the user guide, the AI connector's and StartOS's documents and the store listing describe all of 2.0; connecting an AI is optional and off until you turn it on.
- **The dashboard's Unrealized Gains/Losses** adds up your accounts' own gains, so it matches the Wallet (BTC) and Exchange (BTC) lines when opened; it can differ from alpha.3's by a few cents. It's on no tax form.
- **Coinbase files: the fee is now counted** (a tax-figures fix, #789). In alpha.1–alpha.3, the ready-made Coinbase mapping read a Coinbase file in its current 13-column shape wrongly: a buy's cost basis left out Coinbase's fee (for example $33.01 recorded for a $35.00 buy), and a sale's proceeds came out too high ($16.15 for $15.91 received), so gains were overstated. Now the basis is what was paid and the proceeds are what was received, read from Coinbase's Total; older Coinbase files give the same figures as before. It affects any tax year with Coinbase buys or sales imported from a current-shape Coinbase file in a pre-release. **What to do:** delete those imported rows and import the file again in beta.1 (or edit each row: the Total as its cost or proceeds, and its fee $0), then check Ledger Review.
- **Fixes**, among them: Coinbase's file reads Advance Trade rows, Reward Income and its older fee column; the importer asks for the file's exchange before Preview; a dialog's buttons fit a phone's screen; the transaction panel keeps the keyboard (Tab stays in it, and focus comes back when it closes); Save says why it waits when the coins chosen don't add up.
- **Update your AI connector**: in your AI app's configuration, change the version after btctx-mcp== to 2.0.0b1, then restart the AI app.
- **Reload BitcoinTX's page** in your browser to see them.

Updating from alpha.3 changes no stored figure. StartOS won't install an alpha over it; the StartOS backup you made under 1.x still takes it back to 1.x (below).

**Coming from 1.x**

- **Before you sideload it, make a StartOS backup of BitcoinTX, and keep it**: it's your way back to 1.x. A later backup of BitcoinTX to the same drive replaces it, so back the beta up to another drive. **Download BitcoinTX's own backup too** (Settings, Backup & Restore).
- **Coming from 1.2.9?** The beta has every 1.x fix up to 1.2.10. Read [1.2.10's notes](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) first: four of its fixes can change a tax figure, each with what to do.
- **After updating**, reload BitcoinTX's page and update your AI connector (above): once your ledger has a second wallet or exchange, an older connector can still read it, but BitcoinTX refuses its changes, and a ledger with an extra bitcoin account made through 1.x's account API has two wallets as soon as it's updated. Every transaction keeps its account, and your figures don't change, except in a ledger started before 0.9.2: a transaction saved then into an account made through BitcoinTX's old account API now counts by that account's currency, so its income, rebates and gifts can move, and once the ledger is recalculated a spend's network fee from it lowers the spend's proceeds and gain. Ledger Review lists these rows ("Transactions in an account made through BitcoinTX's old account API"): check each, then run Recalculate Ledger. Before the update BitcoinTX keeps a copy of your 1.x database, backups/btctx-pre-2.0-….db, so BitcoinTX's data takes about twice the space (one copy, made once); it never deletes that copy.
- **What's new in 2.0**: your wallets, exchanges and banks, added in Settings (Wallets, exchanges and banks), each wallet and exchange with its own coins; Form 8949 per exchange; an importer for any exchange's CSV file; a question before an earlier tax year's figures move. [alpha.1's notes](${ALPHA_1}) say more.

**Going back to 1.x**

Uninstall BitcoinTX (which deletes the beta's data, the copy above included) and restore the StartOS backup you made before: it brings back 1.x with its records. Without it, sideload 1.x from its GitHub release and restore, in its Settings, the BitcoinTX backup you downloaded under 1.x. What you entered in the beta can't go back: 1.x can't read a 2.0 database or backup. While a server runs an alpha or a beta, StartOS offers it no 1.x update: fixes come in the next pre-release.

[Everything in 2.0.0-beta.1](${CHANGELOG})`,
    es_ES: `**Esta es la primera beta de BitcoinTX 2.0: una versión preliminar para probar la 2.0 antes de su lanzamiento. No guardes en ella tus registros reales.** Una beta sigue a las alfas: trae toda la 2.0, que se prueba en conjunto. Sigue siendo una versión preliminar en GitHub: nadie la recibe como actualización, la instalas tú mismo con Sideload, puede tener errores, y la tienda de Start9 sigue en BitcoinTX 1.x, la versión para tus registros.

**Novedades desde la 2.0.0-alpha.3**

- **Los textos dicen lo que hace la 2.0.** El coste base es Per-wallet FIFO: cada monedero y cada exchange usa primero sus propias monedas más antiguas, y en un monedero propio puedes elegir qué monedas salen, si las elegiste cuando salieron. El README, la guía de uso, los documentos del conector de IA y de StartOS y la ficha de la tienda describen toda la 2.0; conectar una IA es opcional y está desactivado hasta que lo actives.
- **Unrealized Gains/Losses del panel** suma las ganancias propias de tus cuentas, así que coincide con las líneas Wallet (BTC) y Exchange (BTC) al abrirlas; puede diferir de la de la alpha.3 en unos céntimos. No figura en ningún formulario fiscal.
- **Archivos de Coinbase: ahora se cuenta la comisión** (una corrección de cifras fiscales, #789). De la alpha.1 a la alpha.3, la correspondencia ya hecha de Coinbase leía mal un archivo de Coinbase en su forma actual de 13 columnas: el coste base de una compra dejaba fuera la comisión de Coinbase (por ejemplo, $33.01 registrados por una compra de $35.00), y el importe de una venta salía demasiado alto ($16.15 por $15.91 recibidos), así que las ganancias quedaban infladas. Ahora el coste base es lo pagado y el importe es lo recibido, leídos del Total de Coinbase; los archivos de Coinbase más antiguos dan las mismas cifras que antes. Afecta a cualquier año fiscal con compras o ventas de Coinbase importadas en una versión preliminar desde un archivo de Coinbase de forma actual. **Qué hacer:** borra esas filas importadas e importa el archivo de nuevo en la beta.1 (o edita cada fila: el Total como su coste o importe, y su comisión a $0), y después revisa Ledger Review.
- **Correcciones**, entre ellas: el archivo de Coinbase lee las filas Advance Trade, Reward Income y su antigua columna de comisiones; el importador pide el exchange del archivo antes de Preview; los botones de un diálogo caben en la pantalla de un teléfono; el panel de transacciones conserva el teclado (Tab se queda en él, y el foco vuelve al cerrarlo); Save explica por qué espera cuando las monedas elegidas no suman lo que sale.
- **Actualiza tu conector de IA**: en la configuración de tu aplicación de IA, cambia la versión que sigue a btctx-mcp== por 2.0.0b1 y reinicia la aplicación de IA.
- **Vuelve a cargar la página de BitcoinTX** en tu navegador para ver los cambios.

Actualizar desde la 2.0.0-alpha.3 no cambia ninguna cifra guardada. StartOS no permite instalar encima una alfa; la copia de seguridad de StartOS que hiciste con la 1.x sigue devolviéndolo a la 1.x (abajo).

**Si vienes de la 1.x**

- **Antes de instalarla, haz una copia de seguridad de BitcoinTX en StartOS y guárdala**: es tu forma de volver a la 1.x. Una copia posterior de BitcoinTX en la misma unidad la sustituye, así que haz las copias de la beta en otra unidad. **Descarga también la copia de seguridad propia de BitcoinTX** (Settings, Backup & Restore).
- **¿Vienes de la 1.2.9?** La beta trae todas las correcciones de la 1.x hasta la 1.2.10. Lee antes [las notas de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cuatro de sus correcciones pueden cambiar una cifra fiscal, cada una con lo que hay que hacer.
- **Después de actualizar**, vuelve a cargar la página de BitcoinTX y actualiza tu conector de IA (arriba): cuando tu libro contable tenga un segundo monedero o exchange, un conector anterior aún puede leerlo, pero BitcoinTX rechaza sus cambios, y un libro contable con una cuenta de bitcoin adicional creada mediante la API de cuentas de la 1.x tiene dos monederos en cuanto se actualiza. Cada transacción conserva su cuenta, y tus cifras no cambian, salvo en un libro contable empezado antes de la 0.9.2: una transacción guardada entonces en una cuenta creada con la antigua API de cuentas de BitcoinTX ahora se cuenta según la moneda de esa cuenta, así que sus ingresos, rebates y regalos recibidos pueden cambiar, y, una vez recalculado el libro contable, la comisión de red de un gasto desde esa cuenta reduce el importe recibido y la ganancia de ese gasto. Ledger Review muestra estas filas ("Transactions in an account made through BitcoinTX's old account API"): revisa cada una y después ejecuta Recalculate Ledger. Antes de actualizar, BitcoinTX guarda una copia de tu base de datos de la 1.x, backups/btctx-pre-2.0-….db, así que sus datos pasan a ocupar más o menos el doble (una sola copia); nunca borra esa copia.
- **Novedades de la 2.0**: tus monederos, exchanges y bancos, añadidos en Settings (Wallets, exchanges and banks), cada monedero y cada exchange con sus propias monedas; el formulario 8949 por exchange; un importador para el archivo CSV de cualquier exchange; una pregunta antes de que cambien las cifras de un año fiscal anterior. Más detalles en [las notas de la 2.0.0-alpha.1](${ALPHA_1}).

**Volver a la 1.x**

Desinstala BitcoinTX (lo que borra los datos de la beta, incluida la copia de arriba) y restaura la copia de seguridad de StartOS que hiciste antes: vuelve la 1.x con sus registros. Sin ella, instala la 1.x desde su versión en GitHub con Sideload y restaura, en su Settings, la copia de BitcoinTX que descargaste con la 1.x. Lo que hayas introducido en la beta no puede volver: la 1.x no puede leer una base de datos ni una copia de la 2.0. Mientras un servidor tenga una alfa o una beta, StartOS no le ofrece actualizaciones de la 1.x: las correcciones llegan en la siguiente versión preliminar.

[Todo lo de la 2.0.0-beta.1](${CHANGELOG})`,
    de_DE: `**Dies ist die erste Beta von BitcoinTX 2.0: eine Vorabversion, um 2.0 vor der Veröffentlichung auszuprobieren. Bewahre darin nicht deine echten Daten auf.** Eine Beta folgt auf die Alphas: Sie enthält ganz 2.0, das als Ganzes getestet wird. Sie ist weiterhin eine Vorabversion auf GitHub: Niemand bekommt sie als Update, du installierst sie selbst per Sideload, sie kann Fehler haben, und Start9s Store bleibt bei BitcoinTX 1.x, der Version für deine Daten.

**Neu seit 2.0.0-alpha.3**

- **Die Texte sagen, was 2.0 tut.** Die Anschaffungskosten folgen Per-wallet FIFO: Jede Wallet und jede Börse verwendet zuerst ihre eigenen ältesten Coins, und in einer eigenen Wallet kannst du wählen, welche Coins sie verlassen, wenn du sie bei ihrem Abgang gewählt hast. Das README, die Bedienungsanleitung, die Dokumente des KI-Connectors und von StartOS und die Beschreibung im Store beschreiben ganz 2.0; eine KI anzubinden ist optional und aus, bis du es einschaltest.
- **Unrealized Gains/Losses im Dashboard** addiert die eigenen Gewinne deiner Konten und stimmt so mit den geöffneten Zeilen Wallet (BTC) und Exchange (BTC) überein; gegenüber alpha.3 kann es um einige Cent abweichen. Es steht auf keinem Steuerformular.
- **Coinbase-Dateien: Die Gebühr zählt jetzt mit** (eine Korrektur von Steuerzahlen, #789). In alpha.1 bis alpha.3 las die fertige Zuordnung für Coinbase eine Coinbase-Datei in ihrer aktuellen Form mit 13 Spalten falsch: Die Anschaffungskosten eines Kaufs ließen die Gebühr von Coinbase weg (zum Beispiel $33.01 erfasst für einen Kauf über $35.00), und der Erlös eines Verkaufs fiel zu hoch aus ($16.15 bei $15.91 erhalten), sodass Gewinne zu hoch waren. Jetzt sind die Anschaffungskosten das Bezahlte und der Erlös das Erhaltene, gelesen aus dem Total von Coinbase; ältere Coinbase-Dateien ergeben dieselben Zahlen wie bisher. Betroffen ist jedes Steuerjahr mit Käufen oder Verkäufen bei Coinbase, die in einer Vorabversion aus einer Coinbase-Datei in aktueller Form importiert wurden. **Was zu tun ist:** Lösche diese importierten Zeilen und importiere die Datei in beta.1 erneut (oder bearbeite jede Zeile: das Total als Kosten oder Erlös und die Gebühr auf $0), dann prüfe Ledger Review.
- **Korrekturen**, darunter: Die Datei von Coinbase liest Advance-Trade-Zeilen, Reward Income und ihre ältere Gebührenspalte; der Import fragt vor Preview nach der Börse der Datei; die Schaltflächen eines Dialogs passen auf den Bildschirm eines Telefons; das Transaktionsfeld behält die Tastatur (Tab bleibt darin, und der Fokus kehrt beim Schließen zurück); Save sagt, warum es wartet, wenn die gewählten Coins nicht aufgehen.
- **Aktualisiere deinen KI-Connector**: Ändere in der Konfiguration deiner KI-App die Version nach btctx-mcp== in 2.0.0b1 und starte die KI-App neu.
- **Lade die Seite von BitcoinTX** in deinem Browser neu, um die Änderungen zu sehen.

Das Update von 2.0.0-alpha.3 ändert keine gespeicherte Zahl. StartOS installiert keine Alpha wieder darüber; die StartOS-Sicherung, die du unter 1.x erstellt hast, bringt es weiterhin zu 1.x zurück (unten).

**Wenn du von 1.x kommst**

- **Erstelle vor der Installation eine StartOS-Sicherung von BitcoinTX und bewahre sie auf**: Sie ist dein Weg zurück zu 1.x. Eine spätere Sicherung von BitcoinTX auf dasselbe Laufwerk ersetzt sie, sichere die Beta also auf ein anderes Laufwerk. **Lade auch die eigene Sicherung von BitcoinTX herunter** (Settings, Backup & Restore).
- **Du kommst von 1.2.9?** Die Beta enthält jede 1.x-Korrektur bis 1.2.10. Lies zuerst [die Hinweise zu 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): Vier ihrer Korrekturen können eine Steuerzahl ändern, jede mit dem, was zu tun ist.
- **Nach dem Update** lade die Seite von BitcoinTX neu und aktualisiere deinen KI-Connector (oben): Sobald dein Journal eine zweite Wallet oder Börse hat, kann ein älterer Connector es noch lesen, aber BitcoinTX lehnt seine Änderungen ab, und ein Journal mit einem zusätzlichen Bitcoin-Konto, das über die Konten-API von 1.x angelegt wurde, hat gleich nach dem Update zwei Wallets. Jede Transaktion behält ihr Konto, und deine Zahlen ändern sich nicht, außer in einem Journal, das vor 0.9.2 begonnen wurde: Eine Transaktion, die damals in einem über die alte Konten-API von BitcoinTX angelegten Konto gespeichert wurde, zählt jetzt nach der Währung dieses Kontos. Deren Einkünfte, Rebates und erhaltene Geschenke können sich dadurch verschieben, und nach einer Neuberechnung des Journals senkt die Netzwerkgebühr einer Ausgabe daraus deren Erlös und Gewinn. Ledger Review listet diese Zeilen auf ("Transactions in an account made through BitcoinTX's old account API"): Prüfe jede, dann führe Recalculate Ledger aus. Vor dem Update legt BitcoinTX eine Kopie deiner 1.x-Datenbank an, backups/btctx-pre-2.0-….db, seine Daten brauchen also einmal etwa doppelt so viel Platz; diese Kopie löscht BitcoinTX nie.
- **Neu in 2.0**: deine Wallets, Börsen und Banken, angelegt in Settings (Wallets, exchanges and banks), jede Wallet und jede Börse mit ihren eigenen Coins; Formular 8949 pro Börse; ein Import für die CSV-Datei jeder Börse; eine Frage, bevor sich die Zahlen eines früheren Steuerjahres verschieben. Mehr dazu in [den Hinweisen zu 2.0.0-alpha.1](${ALPHA_1}).

**Zurück zu 1.x**

Deinstalliere BitcoinTX (das löscht die Daten der Beta, die Kopie oben eingeschlossen) und stelle die StartOS-Sicherung wieder her, die du vorher erstellt hast: Sie bringt 1.x mit seinen Daten zurück. Ohne sie installiere 1.x aus seinem GitHub-Release per Sideload und stelle in seinen Settings die BitcoinTX-Sicherung wieder her, die du unter 1.x heruntergeladen hast. Was du in der Beta eingegeben hast, kann nicht zurück: 1.x kann keine Datenbank und keine Sicherung von 2.0 lesen. Solange ein Server eine Alpha oder Beta ausführt, bietet StartOS ihm kein 1.x-Update an: Korrekturen kommen in der nächsten Vorabversion.

[Alles in 2.0.0-beta.1](${CHANGELOG})`,
    pl_PL: `**To pierwsza beta BitcoinTX 2.0: wersja wstępna do wypróbowania 2.0 przed jej wydaniem. Nie trzymaj w niej swoich prawdziwych danych.** Beta przychodzi po alfach: zawiera całe 2.0, testowane jako całość. To nadal wersja wstępna na GitHubie: nikt nie dostaje jej jako aktualizacji, instalujesz ją sam przez Sideload, może zawierać błędy, a sklep Start9 pozostaje przy BitcoinTX 1.x, wersji dla Twoich danych.

**Nowości od 2.0.0-alpha.3**

- **Teksty mówią, co robi 2.0.** Koszt nabycia liczy się metodą Per-wallet FIFO: każdy portfel i każda giełda najpierw wydaje własne najstarsze monety, a w portfelu, którym zarządzasz sam, możesz wybrać, które monety wychodzą, jeśli wybrałeś je w chwili ich wyjścia. README, przewodnik użytkownika, dokumenty łącznika AI i StartOS oraz opis w sklepie opisują całe 2.0; podłączenie AI jest opcjonalne i wyłączone, dopóki go nie włączysz.
- **Unrealized Gains/Losses na panelu** sumuje zyski Twoich kont, więc zgadza się z otwartymi wierszami Wallet (BTC) i Exchange (BTC); może różnić się od wartości z alpha.3 o kilka centów. Nie trafia na żaden formularz podatkowy.
- **Pliki Coinbase: opłata jest teraz liczona** (poprawka wyników podatkowych, #789). W wersjach od alpha.1 do alpha.3 gotowe dopasowanie dla Coinbase źle odczytywało plik Coinbase w obecnej postaci z 13 kolumnami: koszt nabycia zakupu pomijał opłatę Coinbase (na przykład $33.01 zapisane dla zakupu za $35.00), a przychód ze sprzedaży wychodził za wysoki ($16.15 przy otrzymanych $15.91), więc zyski były zawyżone. Teraz koszt nabycia to kwota zapłacona, a przychód to kwota otrzymana, odczytane z kolumny Total Coinbase; starsze pliki Coinbase dają te same wyniki co wcześniej. Dotyczy to każdego roku podatkowego z zakupami lub sprzedażami na Coinbase zaimportowanymi w wersji wstępnej z pliku Coinbase w obecnej postaci. **Co zrobić:** usuń te zaimportowane wiersze i zaimportuj plik ponownie w wersji beta.1 (albo popraw każdy wiersz: wartość Total jako koszt lub przychód, a opłatę na $0), a potem sprawdź Ledger Review.
- **Poprawki**, między innymi: plik Coinbase odczytuje wiersze Advance Trade, Reward Income i starszą kolumnę opłat; import pyta o giełdę pliku przed Preview; przyciski okna dialogowego mieszczą się na ekranie telefonu; panel transakcji zatrzymuje klawiaturę (Tab pozostaje w nim, a fokus wraca po jego zamknięciu); Save mówi, dlaczego czeka, gdy wybrane monety nie dają właściwej sumy.
- **Zaktualizuj łącznik AI**: w konfiguracji aplikacji AI zmień wersję po btctx-mcp== na 2.0.0b1 i uruchom aplikację AI ponownie.
- **Odśwież stronę BitcoinTX** w przeglądarce, aby zobaczyć zmiany.

Aktualizacja z 2.0.0-alpha.3 nie zmienia żadnego zapisanego wyniku. StartOS nie pozwoli zainstalować z powrotem alfy; kopia zapasowa StartOS zrobiona w 1.x nadal przywraca 1.x (niżej).

**Jeśli przechodzisz z 1.x**

- **Przed instalacją zrób kopię zapasową BitcoinTX w StartOS i zachowaj ją**: to Twoja droga powrotu do 1.x. Późniejsza kopia BitcoinTX na tym samym dysku ją zastępuje, więc kopie bety rób na innym dysku. **Pobierz też własną kopię zapasową BitcoinTX** (Settings, Backup & Restore).
- **Przechodzisz z 1.2.9?** Beta zawiera wszystkie poprawki 1.x do wersji 1.2.10. Najpierw przeczytaj [informacje o 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cztery z jej poprawek mogą zmienić wynik podatkowy, każda z opisem, co zrobić.
- **Po aktualizacji** odśwież stronę BitcoinTX i zaktualizuj łącznik AI (wyżej): gdy Twoja księga ma drugi portfel lub drugą giełdę, starszy łącznik nadal może ją czytać, ale BitcoinTX odrzuca jego zmiany, a księga z dodatkowym kontem bitcoinowym utworzonym przez API kont 1.x ma dwa portfele od razu po aktualizacji. Każda transakcja zachowuje swoje konto, a Twoje wyniki się nie zmieniają, z wyjątkiem księgi założonej przed 0.9.2: transakcja zapisana wtedy na koncie utworzonym przez dawne API kont BitcoinTX liczy się teraz według waluty tego konta, więc dochody, rebate i otrzymane prezenty z tego konta mogą się zmienić, a po przeliczeniu księgi opłata sieciowa wydatku z tego konta obniża przychód i zysk z tego wydatku. Ledger Review wymienia te wiersze ("Transactions in an account made through BitcoinTX's old account API"): sprawdź każdy, a potem uruchom Recalculate Ledger. Przed aktualizacją BitcoinTX zachowuje kopię bazy danych 1.x, backups/btctx-pre-2.0-….db, więc jednorazowo jego dane zajmują mniej więcej dwa razy więcej miejsca; tej kopii nigdy nie usuwa.
- **Nowości w 2.0**: Twoje portfele, giełdy i banki, dodane w Settings (Wallets, exchanges and banks), każdy portfel i każda giełda z własnymi monetami; formularz 8949 dla każdej giełdy; import pliku CSV z dowolnej giełdy; pytanie, zanim zmienią się wyniki wcześniejszego roku podatkowego. Więcej w [informacjach o 2.0.0-alpha.1](${ALPHA_1}).

**Powrót do 1.x**

Odinstaluj BitcoinTX (co usuwa dane bety, łącznie z kopią opisaną wyżej) i przywróć kopię zapasową StartOS zrobioną wcześniej: wraca 1.x z jej danymi. Bez niej zainstaluj 1.x z jej wydania na GitHubie przez Sideload i przywróć w jej Settings kopię BitcoinTX pobraną w 1.x. Tego, co wprowadzisz w becie, nie da się przenieść z powrotem: 1.x nie odczyta bazy danych ani kopii zapasowej z 2.0. Dopóki serwer ma alfę lub betę, StartOS nie proponuje mu aktualizacji 1.x: poprawki przychodzą w kolejnej wersji wstępnej.

[Wszystko w 2.0.0-beta.1](${CHANGELOG})`,
    fr_FR: `**Voici la première bêta de BitcoinTX 2.0 : une préversion pour essayer la 2.0 avant sa sortie. N’y gardez pas vos vrais registres.** Une bêta suit les alphas : elle contient toute la 2.0, testée dans son ensemble. C’est toujours une préversion sur GitHub : personne ne la reçoit en mise à jour, vous l’installez vous-même par Sideload, elle peut contenir des bugs, et la boutique de Start9 reste sur BitcoinTX 1.x, la version pour vos registres.

**Nouveautés depuis la 2.0.0-alpha.3**

- **Les textes disent ce que fait la 2.0.** Le coût d’acquisition suit le Per-wallet FIFO : chaque portefeuille et chaque plateforme utilise d’abord ses propres bitcoins les plus anciens, et dans un portefeuille que vous gérez vous-même, vous pouvez choisir quels bitcoins partent, si vous les avez choisis au moment de leur départ. Le README, le guide d’utilisation, les documents du connecteur IA et de StartOS et la fiche de la boutique décrivent toute la 2.0 ; connecter une IA est facultatif et désactivé tant que vous ne l’activez pas.
- **Unrealized Gains/Losses du tableau de bord** additionne les gains propres à vos comptes et correspond donc aux lignes Wallet (BTC) et Exchange (BTC) une fois ouvertes ; il peut différer de quelques centimes de celui de l’alpha.3. Il ne figure sur aucun formulaire fiscal.
- **Fichiers Coinbase : les frais sont maintenant comptés** (une correction de chiffres fiscaux, #789). De l’alpha.1 à l’alpha.3, la correspondance toute prête pour Coinbase lisait mal un fichier Coinbase dans sa forme actuelle à 13 colonnes : le coût d’acquisition d’un achat omettait les frais de Coinbase (par exemple $33.01 enregistrés pour un achat de $35.00), et le produit d’une vente sortait trop élevé ($16.15 pour $15.91 reçus), si bien que les gains étaient surévalués. Désormais, le coût d’acquisition est ce qui a été payé et le produit ce qui a été reçu, lus dans le Total de Coinbase ; les fichiers Coinbase plus anciens donnent les mêmes chiffres qu’avant. Cela concerne toute année fiscale avec des achats ou ventes Coinbase importés dans une préversion depuis un fichier Coinbase de forme actuelle. **Que faire :** supprimez ces lignes importées et importez à nouveau le fichier dans la bêta.1 (ou modifiez chaque ligne : le Total comme coût ou produit, et ses frais à $0), puis vérifiez Ledger Review.
- **Des corrections**, entre autres : le fichier de Coinbase lit les lignes Advance Trade, Reward Income et son ancienne colonne de frais ; l’import demande la plateforme du fichier avant Preview ; les boutons d’une boîte de dialogue tiennent sur l’écran d’un téléphone ; le panneau de transaction garde le clavier (Tab y reste, et le focus revient à sa fermeture) ; Save dit pourquoi il attend quand les bitcoins choisis ne font pas le compte.
- **Mettez à jour votre connecteur IA** : dans la configuration de votre application d’IA, remplacez la version après btctx-mcp== par 2.0.0b1 et redémarrez l’application d’IA.
- **Rechargez la page de BitcoinTX** dans votre navigateur pour voir ces changements.

La mise à jour depuis la 2.0.0-alpha.3 ne change aucun chiffre enregistré. StartOS ne réinstalle pas une alpha par-dessus ; la sauvegarde StartOS faite sous la 1.x le ramène toujours à la 1.x (ci-dessous).

**Si vous venez de la 1.x**

- **Avant de l’installer, faites une sauvegarde StartOS de BitcoinTX, et gardez-la** : c’est votre chemin de retour vers la 1.x. Une sauvegarde ultérieure de BitcoinTX sur le même disque la remplace : sauvegardez donc la bêta sur un autre disque. **Téléchargez aussi la sauvegarde propre à BitcoinTX** (Settings, Backup & Restore).
- **Vous venez de la 1.2.9 ?** La bêta contient toutes les corrections de la 1.x jusqu’à la 1.2.10. Lisez d’abord [les notes de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) : quatre de ses corrections peuvent changer un chiffre fiscal, chacune avec ce qu’il faut faire.
- **Après la mise à jour**, rechargez la page de BitcoinTX et mettez à jour votre connecteur IA (ci-dessus) : dès que votre registre a un deuxième portefeuille ou une deuxième plateforme, un connecteur plus ancien peut encore le lire, mais BitcoinTX refuse ses modifications, et un registre avec un compte bitcoin supplémentaire créé via l’API des comptes de la 1.x a deux portefeuilles dès la mise à jour. Chaque transaction garde son compte, et vos chiffres ne changent pas, sauf dans un registre commencé avant la 0.9.2 : une transaction enregistrée alors dans un compte créé par l’ancienne API des comptes de BitcoinTX compte désormais selon la devise de ce compte ; ses revenus, rebates et dons reçus peuvent changer, et une fois le registre recalculé, les frais de réseau d’une dépense faite depuis ce compte réduisent le produit et le gain de cette dépense. Ledger Review liste ces lignes ("Transactions in an account made through BitcoinTX's old account API") : vérifiez chacune, puis lancez Recalculate Ledger. Avant la mise à jour, BitcoinTX garde une copie de votre base de données 1.x, backups/btctx-pre-2.0-….db : ses données prennent donc environ deux fois plus de place (une seule copie) ; BitcoinTX ne supprime jamais cette copie.
- **Nouveautés de la 2.0** : vos portefeuilles, plateformes et banques, ajoutés dans Settings (Wallets, exchanges and banks), chaque portefeuille et chaque plateforme avec ses propres bitcoins ; le formulaire 8949 par plateforme ; un import pour le fichier CSV de n’importe quelle plateforme ; une question avant que les chiffres d’une année fiscale antérieure ne bougent. [Les notes de la 2.0.0-alpha.1](${ALPHA_1}) en disent plus.

**Revenir à la 1.x**

Désinstallez BitcoinTX (ce qui efface les données de la bêta, y compris la copie ci-dessus) et restaurez la sauvegarde StartOS faite avant : elle ramène la 1.x avec ses registres. Sans elle, installez la 1.x depuis sa version GitHub par Sideload et restaurez, dans ses Settings, la sauvegarde BitcoinTX téléchargée sous la 1.x. Ce que vous avez saisi dans la bêta ne peut pas revenir : la 1.x ne lit ni une base de données ni une sauvegarde de la 2.0. Tant qu’un serveur fait tourner une alpha ou une bêta, StartOS ne lui propose aucune mise à jour 1.x : les corrections arrivent dans la préversion suivante.

[Tout ce que contient la 2.0.0-beta.1](${CHANGELOG})`,
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})

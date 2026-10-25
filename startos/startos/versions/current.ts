import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.0-alpha.2/docs/CHANGELOG.md'

const ALPHA_1 =
  'https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0-alpha.1'

/**
 * 2.0.0-alpha.2:0, 2.0's second pre-release (B10a; the owner's decision 28
 * on #251: alphas, then betas), sideloaded from its GitHub pre-release, never
 * on Start9's registries. 2.0.0-alpha.1:0's migration was empty, so it is
 * bumped in place (Start9's versions.md), with no migration of its own: the
 * app migrates its database itself. Its notes say what's new since alpha.1,
 * and keep, for a tester coming straight from 1.x, the backup first and the
 * way back.
 */
export const current = VersionInfo.of({
  version: '2.0.0-alpha.2:0',
  releaseNotes: {
    en_US: `**This is BitcoinTX 2.0's second alpha: a pre-release for trying 2.0 before it's released. Don't keep your real records in it.** Nobody gets it as an update: you sideload it yourself, it may have bugs, and Start9's store stays on BitcoinTX 1.x.

**New since 2.0.0-alpha.1**

- **The dashboard looks like 1.2.10's again**: one Portfolio Overview card with your bank, exchange and wallet balances, then Total BTC, the average cost and the unrealized gain. With more than one wallet, exchange or bank, an arrow after that line's name shows each account's balance. No figure changes.
- **A banner above every page says it's a test version**: "BitcoinTX · 2.0.0-alpha.2: a test version, not a release".
- **The store listing's description is reworded**, in all five languages.
- **Update your AI connector**: in your AI app's configuration, change the version after btctx-mcp== to 2.0.0a2, then restart the AI app.

Updating from alpha.1 changes no figure. StartOS can't take BitcoinTX back to alpha.1; the StartOS backup you made under 1.x still takes it back to 1.x (below).

**Coming from 1.x**

- **Before you sideload it, make a StartOS backup of BitcoinTX, and keep it**: it's your way back to 1.x. A later backup of BitcoinTX to the same drive replaces it, so back the alpha up to another drive. **Download BitcoinTX's own backup too** (Settings, Backup & Restore).
- **Coming from 1.2.9?** The alpha has every 1.x fix up to 1.2.10. Read [1.2.10's notes](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) first: four of its fixes can change a tax figure, each with what to do.
- **After updating**, reload BitcoinTX's page and update your AI connector (above): once your ledger has a second wallet or exchange, BitcoinTX refuses an older connector's changes. Every transaction keeps its account, and your figures don't change, except in a ledger started before 0.9.2: a transaction saved then into an account made through BitcoinTX's old account API now counts by that account's currency, so its income, rebates and gifts can move, and once the ledger is recalculated a spend's network fee from it lowers the spend's proceeds and gain. Ledger Review lists these rows ("Transactions in an account made through BitcoinTX's old account API"): check each, then run Recalculate Ledger. Before the update BitcoinTX keeps a copy of your 1.x database, backups/btctx-pre-2.0-….db, so BitcoinTX's data takes about twice the space (one copy, made once); it never deletes that copy.
- **What's new in 2.0** (each wallet, exchange and bank with its own coins, Form 8949 per exchange, any exchange's CSV file, a question before an earlier tax year's figures move): [alpha.1's notes](${ALPHA_1}).

**Going back to 1.x**

Uninstall BitcoinTX (which deletes the alpha's data, the copy above included) and restore the StartOS backup you made before: it brings back 1.x with its records. Without it, sideload 1.x from its GitHub release and restore, in its Settings, the BitcoinTX backup you downloaded under 1.x. What you entered in the alpha can't go back: 1.x can't read a 2.0 database or backup. While a server runs an alpha or a beta, StartOS offers it no 1.x update: fixes come in the next pre-release.

[Everything in 2.0.0-alpha.2](${CHANGELOG})`,
    es_ES: `**Esta es la segunda alfa de BitcoinTX 2.0: una versión preliminar para probar la 2.0 antes de su lanzamiento. No guardes en ella tus registros reales.** Nadie la recibe como actualización: la instalas tú mismo con Sideload, puede tener errores, y la tienda de Start9 sigue en BitcoinTX 1.x.

**Novedades desde la 2.0.0-alpha.1**

- **El panel vuelve a ser como el de la 1.2.10**: una sola tarjeta Portfolio Overview con los saldos de tu banco, tu exchange y tu monedero, y después Total BTC, el coste medio y la ganancia no realizada. Con más de un monedero, exchange o banco, una flecha tras el nombre de esa línea muestra el saldo de cada cuenta. Ninguna cifra cambia.
- **Un aviso encima de cada página dice que es una versión de prueba**: "BitcoinTX · 2.0.0-alpha.2: a test version, not a release".
- **La descripción de la ficha de la tienda está reformulada**, en los cinco idiomas.
- **Actualiza tu conector de IA**: en la configuración de tu aplicación de IA, cambia la versión que sigue a btctx-mcp== por 2.0.0a2 y reinicia la aplicación de IA.

Actualizar desde la 2.0.0-alpha.1 no cambia ninguna cifra. StartOS no puede devolver BitcoinTX a la 2.0.0-alpha.1; la copia de seguridad de StartOS que hiciste con la 1.x sigue devolviéndolo a la 1.x (abajo).

**Si vienes de la 1.x**

- **Antes de instalarla, haz una copia de seguridad de BitcoinTX en StartOS y guárdala**: es tu forma de volver a la 1.x. Una copia posterior de BitcoinTX en la misma unidad la sustituye, así que haz las copias de la alfa en otra unidad. **Descarga también la copia de seguridad propia de BitcoinTX** (Settings, Backup & Restore).
- **¿Vienes de la 1.2.9?** La alfa trae todas las correcciones de la 1.x hasta la 1.2.10. Lee antes [las notas de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cuatro de sus correcciones pueden cambiar una cifra fiscal, cada una con lo que hay que hacer.
- **Después de actualizar**, vuelve a cargar la página de BitcoinTX y actualiza tu conector de IA (arriba): cuando tu libro contable tenga un segundo monedero o exchange, BitcoinTX rechaza los cambios de un conector anterior. Cada transacción conserva su cuenta, y tus cifras no cambian, salvo en un libro contable empezado antes de la 0.9.2: una transacción guardada entonces en una cuenta creada con la antigua API de cuentas de BitcoinTX ahora se cuenta según la moneda de esa cuenta, así que sus ingresos, rebates y regalos recibidos pueden cambiar, y, una vez recalculado el libro contable, la comisión de red de un gasto desde esa cuenta reduce el importe recibido y la ganancia de ese gasto. Ledger Review muestra estas filas ("Transactions in an account made through BitcoinTX's old account API"): revisa cada una y después ejecuta Recalculate Ledger. Antes de actualizar, BitcoinTX guarda una copia de tu base de datos de la 1.x, backups/btctx-pre-2.0-….db, así que sus datos pasan a ocupar más o menos el doble (una sola copia); nunca borra esa copia.
- **Novedades de la 2.0** (cada monedero, exchange y banco con sus propias monedas, el formulario 8949 por exchange, el archivo CSV de cualquier exchange, una pregunta antes de que cambien las cifras de un año fiscal anterior): [las notas de la 2.0.0-alpha.1](${ALPHA_1}).

**Volver a la 1.x**

Desinstala BitcoinTX (lo que borra los datos de la alfa, incluida la copia de arriba) y restaura la copia de seguridad de StartOS que hiciste antes: vuelve la 1.x con sus registros. Sin ella, instala la 1.x desde su versión en GitHub con Sideload y restaura, en su Settings, la copia de BitcoinTX que descargaste con la 1.x. Lo que hayas introducido en la alfa no puede volver: la 1.x no puede leer una base de datos ni una copia de la 2.0. Mientras un servidor tenga una alfa o una beta, StartOS no le ofrece actualizaciones de la 1.x: las correcciones llegan en la siguiente versión preliminar.

[Todo lo de la 2.0.0-alpha.2](${CHANGELOG})`,
    de_DE: `**Dies ist die zweite Alpha von BitcoinTX 2.0: eine Vorabversion, um 2.0 vor der Veröffentlichung auszuprobieren. Bewahre darin nicht deine echten Daten auf.** Niemand bekommt sie als Update: Du installierst sie selbst per Sideload, sie kann Fehler haben, und Start9s Store bleibt bei BitcoinTX 1.x.

**Neu seit 2.0.0-alpha.1**

- **Das Dashboard sieht wieder aus wie in 1.2.10**: eine einzige Karte Portfolio Overview mit den Salden deiner Bank, deiner Börse und deiner Wallet, danach Total BTC, die durchschnittlichen Kosten und der nicht realisierte Gewinn. Bei mehr als einer Wallet, Börse oder Bank zeigt ein Pfeil hinter dem Namen dieser Zeile den Saldo jedes Kontos. Keine Zahl ändert sich.
- **Ein Banner über jeder Seite sagt, dass es eine Testversion ist**: "BitcoinTX · 2.0.0-alpha.2: a test version, not a release".
- **Die Beschreibung im Store ist umformuliert**, in allen fünf Sprachen.
- **Aktualisiere deinen KI-Connector**: Ändere in der Konfiguration deiner KI-App die Version nach btctx-mcp== in 2.0.0a2 und starte die KI-App neu.

Das Update von 2.0.0-alpha.1 ändert keine Zahl. StartOS kann BitcoinTX nicht auf 2.0.0-alpha.1 zurücksetzen; die StartOS-Sicherung, die du unter 1.x erstellt hast, bringt es weiterhin zu 1.x zurück (unten).

**Wenn du von 1.x kommst**

- **Erstelle vor der Installation eine StartOS-Sicherung von BitcoinTX und bewahre sie auf**: Sie ist dein Weg zurück zu 1.x. Eine spätere Sicherung von BitcoinTX auf dasselbe Laufwerk ersetzt sie, sichere die Alpha also auf ein anderes Laufwerk. **Lade auch die eigene Sicherung von BitcoinTX herunter** (Settings, Backup & Restore).
- **Du kommst von 1.2.9?** Die Alpha enthält jede 1.x-Korrektur bis 1.2.10. Lies zuerst [die Hinweise zu 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): Vier ihrer Korrekturen können eine Steuerzahl ändern, jede mit dem, was zu tun ist.
- **Nach dem Update** lade die Seite von BitcoinTX neu und aktualisiere deinen KI-Connector (oben): Sobald dein Journal eine zweite Wallet oder Börse hat, lehnt BitcoinTX die Änderungen eines älteren Connectors ab. Jede Transaktion behält ihr Konto, und deine Zahlen ändern sich nicht, außer in einem Journal, das vor 0.9.2 begonnen wurde: Eine Transaktion, die damals in einem über die alte Konten-API von BitcoinTX angelegten Konto gespeichert wurde, zählt jetzt nach der Währung dieses Kontos. Deren Einkünfte, Rebates und erhaltene Geschenke können sich dadurch verschieben, und nach einer Neuberechnung des Journals senkt die Netzwerkgebühr einer Ausgabe daraus deren Erlös und Gewinn. Ledger Review listet diese Zeilen auf ("Transactions in an account made through BitcoinTX's old account API"): Prüfe jede, dann führe Recalculate Ledger aus. Vor dem Update legt BitcoinTX eine Kopie deiner 1.x-Datenbank an, backups/btctx-pre-2.0-….db, seine Daten brauchen also einmal etwa doppelt so viel Platz; diese Kopie löscht BitcoinTX nie.
- **Neu in 2.0** (jede Wallet, Börse und Bank mit ihren eigenen Coins, Formular 8949 pro Börse, die CSV-Datei jeder Börse, eine Frage, bevor sich die Zahlen eines früheren Steuerjahres verschieben): [die Hinweise zu 2.0.0-alpha.1](${ALPHA_1}).

**Zurück zu 1.x**

Deinstalliere BitcoinTX (das löscht die Daten der Alpha, die Kopie oben eingeschlossen) und stelle die StartOS-Sicherung wieder her, die du vorher erstellt hast: Sie bringt 1.x mit seinen Daten zurück. Ohne sie installiere 1.x aus seinem GitHub-Release per Sideload und stelle in seinen Settings die BitcoinTX-Sicherung wieder her, die du unter 1.x heruntergeladen hast. Was du in der Alpha eingegeben hast, kann nicht zurück: 1.x kann keine Datenbank und keine Sicherung von 2.0 lesen. Solange ein Server eine Alpha oder Beta ausführt, bietet StartOS ihm kein 1.x-Update an: Korrekturen kommen in der nächsten Vorabversion.

[Alles in 2.0.0-alpha.2](${CHANGELOG})`,
    pl_PL: `**To druga alfa BitcoinTX 2.0: wersja wstępna do wypróbowania 2.0 przed jej wydaniem. Nie trzymaj w niej swoich prawdziwych danych.** Nikt nie dostaje jej jako aktualizacji: instalujesz ją sam przez Sideload, może zawierać błędy, a sklep Start9 pozostaje przy BitcoinTX 1.x.

**Nowości od 2.0.0-alpha.1**

- **Panel znów wygląda jak w 1.2.10**: jedna karta Portfolio Overview z saldami banku, giełdy i portfela, a pod nimi Total BTC, średni koszt i niezrealizowany zysk. Gdy masz więcej niż jeden portfel, giełdę lub bank, strzałka po nazwie danego wiersza pokazuje saldo każdego konta. Żaden wynik się nie zmienia.
- **Baner nad każdą stroną mówi, że to wersja testowa**: "BitcoinTX · 2.0.0-alpha.2: a test version, not a release".
- **Opis w sklepie ma nowe brzmienie**, we wszystkich pięciu językach.
- **Zaktualizuj łącznik AI**: w konfiguracji aplikacji AI zmień wersję po btctx-mcp== na 2.0.0a2 i uruchom aplikację AI ponownie.

Aktualizacja z 2.0.0-alpha.1 nie zmienia żadnego wyniku. StartOS nie przywróci BitcoinTX do 2.0.0-alpha.1; kopia zapasowa StartOS zrobiona w 1.x nadal przywraca 1.x (niżej).

**Jeśli przechodzisz z 1.x**

- **Przed instalacją zrób kopię zapasową BitcoinTX w StartOS i zachowaj ją**: to Twoja droga powrotu do 1.x. Późniejsza kopia BitcoinTX na tym samym dysku ją zastępuje, więc kopie alfy rób na innym dysku. **Pobierz też własną kopię zapasową BitcoinTX** (Settings, Backup & Restore).
- **Przechodzisz z 1.2.9?** Alfa zawiera wszystkie poprawki 1.x do wersji 1.2.10. Najpierw przeczytaj [informacje o 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10): cztery z jej poprawek mogą zmienić wynik podatkowy, każda z opisem, co zrobić.
- **Po aktualizacji** odśwież stronę BitcoinTX i zaktualizuj łącznik AI (wyżej): gdy Twoja księga ma drugi portfel lub drugą giełdę, BitcoinTX odrzuca zmiany starszego łącznika. Każda transakcja zachowuje swoje konto, a Twoje wyniki się nie zmieniają, z wyjątkiem księgi założonej przed 0.9.2: transakcja zapisana wtedy na koncie utworzonym przez dawne API kont BitcoinTX liczy się teraz według waluty tego konta, więc dochody, rebate i otrzymane prezenty z tego konta mogą się zmienić, a po przeliczeniu księgi opłata sieciowa wydatku z tego konta obniża przychód i zysk z tego wydatku. Ledger Review wymienia te wiersze ("Transactions in an account made through BitcoinTX's old account API"): sprawdź każdy, a potem uruchom Recalculate Ledger. Przed aktualizacją BitcoinTX zachowuje kopię bazy danych 1.x, backups/btctx-pre-2.0-….db, więc jednorazowo jego dane zajmują mniej więcej dwa razy więcej miejsca; tej kopii nigdy nie usuwa.
- **Nowości w 2.0** (każdy portfel, giełda i bank z własnymi monetami, formularz 8949 dla każdej giełdy, plik CSV z dowolnej giełdy, pytanie, zanim zmienią się wyniki wcześniejszego roku podatkowego): [informacje o 2.0.0-alpha.1](${ALPHA_1}).

**Powrót do 1.x**

Odinstaluj BitcoinTX (co usuwa dane alfy, łącznie z kopią opisaną wyżej) i przywróć kopię zapasową StartOS zrobioną wcześniej: wraca 1.x z jej danymi. Bez niej zainstaluj 1.x z jej wydania na GitHubie przez Sideload i przywróć w jej Settings kopię BitcoinTX pobraną w 1.x. Tego, co wprowadzisz w alfie, nie da się przenieść z powrotem: 1.x nie odczyta bazy danych ani kopii zapasowej z 2.0. Dopóki serwer ma alfę lub betę, StartOS nie proponuje mu aktualizacji 1.x: poprawki przychodzą w kolejnej wersji wstępnej.

[Wszystko w 2.0.0-alpha.2](${CHANGELOG})`,
    fr_FR: `**Voici la deuxième alpha de BitcoinTX 2.0 : une préversion pour essayer la 2.0 avant sa sortie. N’y gardez pas vos vrais registres.** Personne ne la reçoit en mise à jour : vous l’installez vous-même par Sideload, elle peut contenir des bugs, et la boutique de Start9 reste sur BitcoinTX 1.x.

**Nouveautés depuis la 2.0.0-alpha.1**

- **Le tableau de bord ressemble de nouveau à celui de la 1.2.10** : une seule carte Portfolio Overview avec les soldes de votre banque, de votre plateforme et de votre portefeuille, puis Total BTC, le coût moyen et le gain latent. Avec plus d’un portefeuille, d’une plateforme ou d’une banque, une flèche après le nom de la ligne montre le solde de chaque compte. Aucun chiffre ne change.
- **Une bannière au-dessus de chaque page indique que c’est une version de test** : "BitcoinTX · 2.0.0-alpha.2: a test version, not a release".
- **La description de la boutique est reformulée**, dans les cinq langues.
- **Mettez à jour votre connecteur IA** : dans la configuration de votre application d’IA, remplacez la version après btctx-mcp== par 2.0.0a2 et redémarrez l’application d’IA.

La mise à jour depuis la 2.0.0-alpha.1 ne change aucun chiffre. StartOS ne peut pas ramener BitcoinTX à la 2.0.0-alpha.1 ; la sauvegarde StartOS faite sous la 1.x le ramène toujours à la 1.x (ci-dessous).

**Si vous venez de la 1.x**

- **Avant de l’installer, faites une sauvegarde StartOS de BitcoinTX, et gardez-la** : c’est votre chemin de retour vers la 1.x. Une sauvegarde ultérieure de BitcoinTX sur le même disque la remplace : sauvegardez donc l’alpha sur un autre disque. **Téléchargez aussi la sauvegarde propre à BitcoinTX** (Settings, Backup & Restore).
- **Vous venez de la 1.2.9 ?** L’alpha contient toutes les corrections de la 1.x jusqu’à la 1.2.10. Lisez d’abord [les notes de la 1.2.10](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v1.2.10) : quatre de ses corrections peuvent changer un chiffre fiscal, chacune avec ce qu’il faut faire.
- **Après la mise à jour**, rechargez la page de BitcoinTX et mettez à jour votre connecteur IA (ci-dessus) : dès que votre registre a un deuxième portefeuille ou une deuxième plateforme, BitcoinTX refuse les modifications d’un connecteur plus ancien. Chaque transaction garde son compte, et vos chiffres ne changent pas, sauf dans un registre commencé avant la 0.9.2 : une transaction enregistrée alors dans un compte créé par l’ancienne API des comptes de BitcoinTX compte désormais selon la devise de ce compte ; ses revenus, rebates et dons reçus peuvent changer, et une fois le registre recalculé, les frais de réseau d’une dépense faite depuis ce compte réduisent le produit et le gain de cette dépense. Ledger Review liste ces lignes ("Transactions in an account made through BitcoinTX's old account API") : vérifiez chacune, puis lancez Recalculate Ledger. Avant la mise à jour, BitcoinTX garde une copie de votre base de données 1.x, backups/btctx-pre-2.0-….db : ses données prennent donc environ deux fois plus de place (une seule copie) ; BitcoinTX ne supprime jamais cette copie.
- **Nouveautés de la 2.0** (chaque portefeuille, plateforme et banque avec ses propres bitcoins, le formulaire 8949 par plateforme, le fichier CSV de n’importe quelle plateforme, une question avant que les chiffres d’une année fiscale antérieure ne bougent) : [les notes de la 2.0.0-alpha.1](${ALPHA_1}).

**Revenir à la 1.x**

Désinstallez BitcoinTX (ce qui efface les données de l’alpha, y compris la copie ci-dessus) et restaurez la sauvegarde StartOS faite avant : elle ramène la 1.x avec ses registres. Sans elle, installez la 1.x depuis sa version GitHub par Sideload et restaurez, dans ses Settings, la sauvegarde BitcoinTX téléchargée sous la 1.x. Ce que vous avez saisi dans l’alpha ne peut pas revenir : la 1.x ne lit ni une base de données ni une sauvegarde de la 2.0. Tant qu’un serveur fait tourner une alpha ou une bêta, StartOS ne lui propose aucune mise à jour 1.x : les corrections arrivent dans la préversion suivante.

[Tout ce que contient la 2.0.0-alpha.2](${CHANGELOG})`,
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})

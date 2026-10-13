import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'
import { storeJson } from '../fileModels/store.json'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/main/docs/CHANGELOG.md'

/**
 * 1.2.8:0: prices at the hour (#144), the price-source redesign (#145, the
 * package's price step and its update task in init/priceSourceTask.ts),
 * inherited bitcoin and consolidation fees (#163), the spend fee fix (#157)
 * and the #134 privacy fix, and the security review's fixes (#151). The
 * migration raises Recalculate Ledger once (init/recalculateTask.ts): #157's
 * corrected figures reach existing transactions only through a recalculation.
 */
export const current = VersionInfo.of({
  version: '1.2.8:0',
  releaseNotes: {
    en_US: `BitcoinTX 1.2.8 values bitcoin at the hour of each transaction, makes where prices come from one clear choice, adds inherited bitcoin and consolidation fees, stops a spend's network fee from counting twice, and brings the fixes of a security review.

**What to do after updating**

- **Recalculate Ledger.** A task asks once. First open Settings > Ledger Review in BitcoinTX: it lists each spend whose figures change, old and new. Then run Recalculate Ledger (here, or in Settings).
- **Confirm where prices come from.** Unless this action sets it, BitcoinTX's Dashboard asks once to confirm your price choice, and asks nobody until you do. If you never made a choice in this action, a task asks once.
- **Log in again.** After this update everyone logs in once more.
- **Update your AI connector.** In your AI app's configuration, change the version after btctx-mcp== to 1.2.8 and restart the AI app. It now lists a sale's or spend's gross proceeds beside the after-fee figure; an older connector could take the fee off twice when it edited one.

**A fix that changes tax figures**

- **A spend's network fee counted twice in its gain.** When you spent bitcoin (a Withdrawal, purpose Spent) with a BTC network fee, the fee was counted as its own disposal but not taken off the spend's proceeds, so the gain came out too high by the fee's value, usually a few dollars. Versions 0.9.2 to 1.2.7, every tax year; it only ever showed more tax, never less. What to do: Ledger Review, then Recalculate Ledger, as above. Whether to amend a filed return over a few dollars is for you or your tax professional to decide.

**Privacy: a price choice made without asking (fixed)**

- Who could be affected: in 1.2.0 to 1.2.7, owners who switched this action to Decide in BitcoinTX instead (called Choose in BitcoinTX before) after it had been set to Off, Public price sites or My Mempool, or who ran Set Login Credentials or a hand-run command while it was set. BitcoinTX could then save Public price sites as your choice in the app without asking, and use it after a switch.
- What could have been sent: requests from your server's address to public sites for Bitcoin's price (CoinGecko, Kraken, Bitstamp or Coinbase) and the block height (Blockchain.info, Blockstream or mempool.space). Never dates, amounts or anything from your ledger; over Tor, not even your address.
- What to do: confirm or change the choice when BitcoinTX asks once after this update (above), or check Settings > Privacy & Network.

**New**

- **Prices at the hour.** Values BitcoinTX fills in from the BTC price (a blank income or rebate value, a Spent's proceeds, a network fee's value) now use the price when the transaction's hour began: the IRS values bitcoin at the date and time. When your choice allows public price sites, BitcoinTX downloads Bitstamp's hourly prices from 2013 once (about 3 MB), each year checked against a fingerprint that comes with this version. Nothing already saved changes: Ledger Review lists, by tax year, values priced at the day that the hour would change, and changes only the ones you apply.
- **One price choice.** This action now offers My Mempool on this server, Public price sites, Nobody, or Decide in BitcoinTX instead, with Use Tor and, for Mempool, a backup of public price sites. A new install asks before it starts. In the app, one price card says where prices come from and when the last one arrived, and the Dashboard, the sidebar and the transaction form say which price a value used. Coinbase and CoinGecko are no longer asked.
- **Inherited bitcoin.** A new deposit source, Inherited: its cost basis is its value on the date of death, and every sale of those coins is long-term, marked INHERITED on Form 8949.
- **Consolidations.** A transfer within the same wallet (or between exchanges BitcoinTX counts as one) records only its network fee, a disposal of your oldest coins.
- **Trust this server.** With Decide in BitcoinTX instead, a Mempool on another home server at its https address can be trusted from the price card.

**Security and smaller fixes**

- From a security review: logging out ends that session everywhere; other people's failed logins no longer slow down a browser that has logged in before; a restore brings back a backup's data and keeps this install's login, AI key and price settings, or changes nothing; every request has limits on size and time; an edit or deletion by the AI connector keeps a backup copy first, and its imports are kept short. The details are published once this version is available.
- An edit can no longer save a negative fee value, and a price under one cent is never stored as $0.

[Everything in 1.2.8](${CHANGELOG})`,
    es_ES: `BitcoinTX 1.2.8 valora el bitcoin a la hora de cada transacción, convierte el origen de los precios en una sola elección clara, añade el bitcoin heredado y las comisiones de consolidación, evita que la comisión de red de un gasto cuente dos veces e incluye las correcciones de una revisión de seguridad.

**Qué hacer después de actualizar**

- **Recalcular el libro contable.** Una tarea lo pide una vez. Primero abre Settings > Ledger Review en BitcoinTX: muestra cada gasto cuyas cifras cambian, con las anteriores y las nuevas. Después ejecuta Recalcular el libro contable (aquí o en Settings).
- **Confirma de dónde vienen los precios.** Salvo que esta acción lo fije, el Dashboard de BitcoinTX pide una vez que confirmes tu elección de precios, y no pregunta a nadie hasta que lo hagas. Si nunca elegiste nada en esta acción, una tarea lo pide una vez.
- **Vuelve a iniciar sesión.** Después de esta actualización todos inician sesión una vez más.
- **Actualiza tu conector de IA.** En la configuración de tu aplicación de IA, cambia la versión que sigue a btctx-mcp== por 1.2.8 y reinicia la aplicación. Ahora muestra los ingresos brutos de una venta o un gasto junto a la cifra tras la comisión; un conector anterior podía restar la comisión dos veces al editar uno.

**Una corrección que cambia cifras fiscales**

- **La comisión de red de un gasto contaba dos veces en su ganancia.** Al gastar bitcoin (un Withdrawal con propósito Spent) con una comisión de red en BTC, la comisión se contaba como una disposición propia pero no se restaba de los ingresos del gasto, así que la ganancia salía más alta por el valor de la comisión, normalmente unos pocos dólares. Versiones 0.9.2 a 1.2.7, todos los años fiscales; solo mostraba más impuesto, nunca menos. Qué hacer: Ledger Review y después Recalcular el libro contable, como arriba. Decidir si rectificar una declaración ya presentada por unos pocos dólares te corresponde a ti o a tu profesional fiscal.

**Privacidad: una elección de precios hecha sin preguntar (corregido)**

- A quién pudo afectar: en las versiones 1.2.0 a 1.2.7, a quienes cambiaron esta acción a Decidir en BitcoinTX en su lugar (antes Elegir en BitcoinTX) después de tenerla en Desactivado, Sitios públicos de precios o Mi Mempool, o ejecutaron Establecer credenciales de acceso o un comando a mano mientras estaba así. BitcoinTX podía entonces guardar Public price sites como tu elección en la aplicación sin preguntar y usarla tras el cambio.
- Qué pudo enviarse: peticiones desde la dirección de tu servidor a sitios públicos, para el precio del bitcoin (CoinGecko, Kraken, Bitstamp o Coinbase) y la altura de bloque (Blockchain.info, Blockstream o mempool.space). Nunca fechas, cantidades ni nada de tu libro contable; por Tor, ni siquiera tu dirección.
- Qué hacer: confirma o cambia la elección cuando BitcoinTX lo pida una vez tras esta actualización (arriba), o revisa Settings > Privacy & Network.

**Novedades**

- **Precios por hora.** Los valores que BitcoinTX rellena con el precio del BTC (un valor de ingreso o de rebate en blanco, los ingresos de un Spent, el valor de una comisión de red) usan ahora el precio del inicio de la hora de la transacción: el IRS valora el bitcoin en la fecha y la hora. Cuando tu elección permite los sitios públicos de precios, BitcoinTX descarga una vez los precios por hora de Bitstamp desde 2013 (unos 3 MB) y comprueba cada año con una huella que viene con esta versión. Nada de lo ya guardado cambia: Ledger Review muestra, por año fiscal, los valores con el precio del día que la hora cambiaría, y solo cambia los que apliques.
- **Una sola elección de precios.** Esta acción ofrece ahora Mi Mempool en este servidor, Sitios públicos de precios, Nadie o Decidir en BitcoinTX en su lugar, con Tor y, para Mempool, los sitios públicos como respaldo. Una instalación nueva lo pregunta antes de arrancar. En la aplicación, una sola tarjeta de precios dice de dónde vienen los precios y cuándo llegó el último, y el Dashboard, la barra lateral y el formulario de transacción dicen qué precio usó cada valor. Ya no se pregunta a Coinbase ni a CoinGecko.
- **Bitcoin heredado.** Un nuevo origen de depósito, Inherited: su coste base es su valor en la fecha del fallecimiento, y toda venta de esas monedas es a largo plazo, marcada INHERITED en el Form 8949.
- **Consolidaciones.** Una transferencia dentro del mismo monedero (o entre exchanges que BitcoinTX cuenta como uno) registra solo su comisión de red, como disposición de tus monedas más antiguas.
- **Confiar en este servidor.** Con Decidir en BitcoinTX en su lugar, un Mempool en otro servidor doméstico con dirección https puede marcarse como de confianza desde la tarjeta de precios.

**Seguridad y correcciones menores**

- De una revisión de seguridad: cerrar sesión termina esa sesión en todas partes; los inicios de sesión fallidos de otros ya no frenan a un navegador que ya inició sesión antes; una restauración trae los datos de la copia y conserva el acceso, la clave de IA y los ajustes de precios de esta instalación, o no cambia nada; cada petición tiene límites de tamaño y de tiempo; una edición o un borrado del conector de IA guarda antes una copia, y sus importaciones son cortas. Los detalles se publican cuando esta versión esté disponible.
- Una edición ya no puede guardar un valor de comisión negativo, y un precio inferior a un centavo nunca se guarda como 0 $.

[Todo lo de la 1.2.8](${CHANGELOG})`,
    de_DE: `BitcoinTX 1.2.8 bewertet Bitcoin zur Stunde jeder Transaktion, macht die Herkunft der Kurse zu einer klaren Wahl, ergänzt geerbte Bitcoin und Konsolidierungsgebühren, verhindert, dass die Netzwerkgebühr einer Ausgabe doppelt zählt, und bringt die Korrekturen einer Sicherheitsprüfung.

**Was nach dem Update zu tun ist**

- **Journal neu berechnen.** Eine Aufgabe fragt einmal danach. Öffne zuerst Settings > Ledger Review in BitcoinTX: Dort steht jede Ausgabe, deren Zahlen sich ändern, alt und neu. Führe dann Journal neu berechnen aus (hier oder in Settings).
- **Bestätige, woher die Kurse kommen.** Sofern diese Aktion es nicht festlegt, bittet das Dashboard von BitcoinTX einmal darum, deine Kurswahl zu bestätigen, und fragt bis dahin niemanden. Hast du in dieser Aktion nie etwas gewählt, fragt eine Aufgabe einmal danach.
- **Melde dich erneut an.** Nach diesem Update melden sich alle noch einmal an.
- **Aktualisiere deinen KI-Connector.** Ändere in der Konfiguration deiner KI-App die Version nach btctx-mcp== in 1.2.8 und starte die App neu. Er zeigt jetzt den Bruttoerlös eines Verkaufs oder einer Ausgabe neben dem Betrag nach Gebühr; ein älterer Connector konnte die Gebühr beim Bearbeiten doppelt abziehen.

**Eine Korrektur, die Steuerzahlen ändert**

- **Die Netzwerkgebühr einer Ausgabe zählte doppelt im Gewinn.** Wurde Bitcoin ausgegeben (eine Withdrawal mit dem Zweck Spent) und eine Netzwerkgebühr in BTC gezahlt, zählte die Gebühr als eigene Veräußerung, wurde aber nicht vom Erlös der Ausgabe abgezogen; der Gewinn war also um den Wert der Gebühr zu hoch, meist ein paar Dollar. Versionen 0.9.2 bis 1.2.7, jedes Steuerjahr; es ergab immer nur mehr Steuer, nie weniger. Was zu tun ist: Ledger Review, dann Journal neu berechnen, wie oben. Ob eine bereits abgegebene Erklärung wegen ein paar Dollar berichtigt wird, entscheidest du oder dein Steuerberater.

**Datenschutz: eine Kurswahl ohne Nachfrage (behoben)**

- Wer betroffen sein konnte: in 1.2.0 bis 1.2.7, wer diese Aktion auf Stattdessen in BitcoinTX entscheiden (früher In BitcoinTX wählen) umgestellt hat, nachdem sie auf Aus, Öffentliche Kursseiten oder Mein Mempool stand, oder wer Zugangsdaten festlegen oder einen Befehl von Hand ausgeführt hat, während sie so stand. BitcoinTX konnte dann ohne Nachfrage Public price sites als deine Wahl in der App speichern und nach der Umstellung verwenden.
- Was gesendet worden sein kann: Anfragen von der Adresse deines Servers an öffentliche Seiten, nach dem Bitcoin-Kurs (CoinGecko, Kraken, Bitstamp oder Coinbase) und der Blockhöhe (Blockchain.info, Blockstream oder mempool.space). Nie Daten, Beträge oder etwas aus deinem Journal; über Tor nicht einmal deine Adresse.
- Was zu tun ist: Bestätige oder ändere die Wahl, wenn BitcoinTX nach diesem Update einmal fragt (oben), oder prüfe Settings > Privacy & Network.

**Neu**

- **Kurse zur Stunde.** Werte, die BitcoinTX aus dem BTC-Kurs einsetzt (ein leerer Einkommens- oder Rebate-Wert, der Erlös eines Spent, der Wert einer Netzwerkgebühr), verwenden jetzt den Kurs zu Beginn der Stunde der Transaktion: Der IRS bewertet Bitcoin nach Datum und Uhrzeit. Erlaubt deine Wahl öffentliche Preisseiten, lädt BitcoinTX die Stundenkurse von Bitstamp ab 2013 einmal herunter (etwa 3 MB) und prüft jedes Jahr gegen einen Fingerabdruck, der mit dieser Version kommt. Nichts bereits Gespeichertes ändert sich: Ledger Review listet nach Steuerjahr die Werte zum Tageskurs auf, die die Stunde ändern würde, und ändert nur die, die du übernimmst.
- **Eine Kurswahl.** Diese Aktion bietet jetzt Mein Mempool auf diesem Server, Öffentliche Preisseiten, Niemand oder Stattdessen in BitcoinTX entscheiden, mit Tor und, für Mempool, öffentlichen Preisseiten als Ersatz. Eine neue Installation fragt vor dem Start. In der App sagt eine Kurskarte, woher die Kurse kommen und wann der letzte kam, und Dashboard, Seitenleiste und Transaktionsformular zeigen, welchen Kurs ein Wert verwendet hat. Coinbase und CoinGecko werden nicht mehr gefragt.
- **Geerbte Bitcoin.** Eine neue Einzahlungsquelle, Inherited: Ihre Anschaffungskosten sind ihr Wert am Todestag, und jeder Verkauf dieser Coins ist langfristig, in Form 8949 mit INHERITED vermerkt.
- **Konsolidierungen.** Ein Transfer innerhalb derselben Wallet (oder zwischen Börsen, die BitcoinTX als eine zählt) erfasst nur seine Netzwerkgebühr, als Veräußerung deiner ältesten Coins.
- **Diesem Server vertrauen.** Mit Stattdessen in BitcoinTX entscheiden kann ein Mempool auf einem anderen Heimserver mit https-Adresse über die Kurskarte als vertrauenswürdig markiert werden.

**Sicherheit und kleinere Korrekturen**

- Aus einer Sicherheitsprüfung: Abmelden beendet diese Sitzung überall; fehlgeschlagene Anmeldungen anderer bremsen einen Browser nicht mehr, der sich schon einmal angemeldet hat; eine Wiederherstellung bringt die Daten einer Sicherung zurück und behält Anmeldung, KI-Schlüssel und Kurseinstellungen dieser Installation, oder ändert nichts; jede Anfrage hat Grenzen für Größe und Zeit; eine Änderung oder Löschung durch den KI-Connector legt vorher eine Sicherungskopie an, und seine Importe bleiben kurz. Die Einzelheiten werden veröffentlicht, sobald diese Version verfügbar ist.
- Eine Änderung kann keinen negativen Gebührenwert mehr speichern, und ein Kurs unter einem Cent wird nie als 0 $ gespeichert.

[Alles in 1.2.8](${CHANGELOG})`,
    pl_PL: `BitcoinTX 1.2.8 wycenia bitcoina według godziny każdej transakcji, sprowadza źródło cen do jednego jasnego wyboru, dodaje odziedziczone bitcoiny i opłaty za konsolidację, sprawia, że opłata sieciowa wydatku nie liczy się podwójnie, i wprowadza poprawki z przeglądu bezpieczeństwa.

**Co zrobić po aktualizacji**

- **Przelicz księgę.** Zadanie poprosi o to raz. Najpierw otwórz Settings > Ledger Review w BitcoinTX: pokazuje każdy wydatek, którego wartości się zmieniają, stare i nowe. Potem uruchom Przelicz księgę (tutaj albo w Settings).
- **Potwierdź, skąd pochodzą ceny.** Jeśli ta akcja tego nie ustawia, Dashboard BitcoinTX raz poprosi o potwierdzenie wyboru źródła cen i do tego czasu nikogo nie pyta. Jeśli w tej akcji nigdy niczego nie wybrano, raz poprosi o to zadanie.
- **Zaloguj się ponownie.** Po tej aktualizacji wszyscy logują się jeszcze raz.
- **Zaktualizuj łącznik AI.** W konfiguracji aplikacji AI zmień wersję po btctx-mcp== na 1.2.8 i uruchom aplikację ponownie. Łącznik pokazuje teraz przychód brutto ze sprzedaży lub wydatku obok kwoty po opłacie; starszy łącznik mógł przy edycji odjąć opłatę dwa razy.

**Poprawka, która zmienia wartości podatkowe**

- **Opłata sieciowa wydatku liczyła się podwójnie w zysku.** Przy wydaniu bitcoina (Withdrawal z celem Spent) z opłatą sieciową w BTC opłata liczyła się jako osobne zbycie, ale nie była odejmowana od przychodu z wydatku, więc zysk wychodził za wysoki o wartość opłaty, zwykle o kilka dolarów. Wersje 0.9.2 do 1.2.7, każdy rok podatkowy; zawsze dawało to wyższy podatek, nigdy niższy. Co zrobić: Ledger Review, potem Przelicz księgę, jak wyżej. Czy korygować złożone już zeznanie z powodu kilku dolarów, decydujesz Ty lub Twój doradca podatkowy.

**Prywatność: wybór źródła cen bez pytania (naprawione)**

- Kogo mogło to dotyczyć: w wersjach 1.2.0 do 1.2.7 tych, którzy przełączyli tę akcję na Zamiast tego zdecyduj w BitcoinTX (wcześniej Wybierz w BitcoinTX) po ustawieniu jej na Wyłączone, Publiczne serwisy z cenami lub Mój Mempool, albo uruchomili Ustaw dane logowania lub polecenie ręcznie przy takim ustawieniu. BitcoinTX mógł wtedy bez pytania zapisać Public price sites jako Twój wybór w aplikacji i użyć go po przełączeniu.
- Co mogło zostać wysłane: zapytania z adresu Twojego serwera do publicznych serwisów o cenę bitcoina (CoinGecko, Kraken, Bitstamp lub Coinbase) i wysokość bloku (Blockchain.info, Blockstream lub mempool.space). Nigdy daty, kwoty ani nic z Twojej księgi; przez Tor nawet nie Twój adres.
- Co zrobić: potwierdź lub zmień wybór, gdy BitcoinTX raz o to zapyta po tej aktualizacji (wyżej), albo sprawdź Settings > Privacy & Network.

**Nowości**

- **Ceny według godziny.** Wartości, które BitcoinTX uzupełnia z ceny BTC (pusta wartość dochodu lub rebate, przychód ze Spent, wartość opłaty sieciowej), używają teraz ceny z początku godziny transakcji: IRS wycenia bitcoina według daty i godziny. Gdy Twój wybór dopuszcza publiczne serwisy cenowe, BitcoinTX raz pobiera godzinowe ceny Bitstamp od 2013 r. (około 3 MB) i sprawdza każdy rok odciskiem dołączonym do tej wersji. Nic już zapisanego się nie zmienia: Ledger Review pokazuje według roku podatkowego wartości wycenione ceną dnia, które godzina by zmieniła, i zmienia tylko te, które zatwierdzisz.
- **Jeden wybór źródła cen.** Ta akcja oferuje teraz Mój Mempool na tym serwerze, Publiczne serwisy cenowe, Nikt albo Zamiast tego zdecyduj w BitcoinTX, z Torem i, dla Mempoola, publicznymi serwisami jako zapasem. Nowa instalacja pyta o to przed uruchomieniem. W aplikacji jedna karta cen mówi, skąd pochodzą ceny i kiedy przyszła ostatnia, a Dashboard, pasek boczny i formularz transakcji pokazują, jakiej ceny użyła dana wartość. Coinbase i CoinGecko nie są już pytane.
- **Odziedziczone bitcoiny.** Nowe źródło wpłaty, Inherited: koszt nabycia to wartość w dniu śmierci, a każda sprzedaż tych monet jest długoterminowa, oznaczona INHERITED w Form 8949.
- **Konsolidacje.** Transfer w obrębie tego samego portfela (lub między giełdami, które BitcoinTX liczy jako jedną) zapisuje tylko opłatę sieciową, jako zbycie Twoich najstarszych monet.
- **Zaufaj temu serwerowi.** Przy Zamiast tego zdecyduj w BitcoinTX Mempool na innym serwerze domowym pod adresem https można oznaczyć jako zaufany na karcie cen.

**Bezpieczeństwo i mniejsze poprawki**

- Z przeglądu bezpieczeństwa: wylogowanie kończy tę sesję wszędzie; nieudane logowania innych osób nie spowalniają już przeglądarki, która logowała się wcześniej; przywracanie przywraca dane z kopii i zachowuje logowanie, klucz AI i ustawienia cen tej instalacji albo niczego nie zmienia; każde zapytanie ma limity rozmiaru i czasu; edycja lub usunięcie przez łącznik AI najpierw zapisuje kopię zapasową, a jego importy są krótkie. Szczegóły zostaną opublikowane, gdy ta wersja będzie dostępna.
- Edycja nie może już zapisać ujemnej wartości opłaty, a cena poniżej jednego centa nigdy nie jest zapisywana jako 0 $.

[Wszystko w 1.2.8](${CHANGELOG})`,
    fr_FR: `BitcoinTX 1.2.8 évalue le bitcoin à l’heure de chaque transaction, fait de l’origine des prix un seul choix clair, ajoute les bitcoins hérités et les frais de consolidation, empêche les frais de réseau d’une dépense de compter deux fois et apporte les corrections d’un audit de sécurité.

**Que faire après la mise à jour**

- **Recalculer le registre.** Une tâche le demande une fois. Ouvrez d’abord Settings > Ledger Review dans BitcoinTX : il liste chaque dépense dont les chiffres changent, anciens et nouveaux. Lancez ensuite Recalculer le registre (ici ou dans Settings).
- **Confirmez d’où viennent les prix.** Sauf si cette action le fixe, le Dashboard de BitcoinTX demande une fois de confirmer votre choix de prix, et n’interroge personne d’ici là. Si vous n’avez jamais fait de choix dans cette action, une tâche le demande une fois.
- **Reconnectez-vous.** Après cette mise à jour, tout le monde se reconnecte une fois.
- **Mettez à jour votre connecteur IA.** Dans la configuration de votre application d’IA, remplacez la version après btctx-mcp== par 1.2.8 et redémarrez l’application. Il affiche désormais le produit brut d’une vente ou d’une dépense à côté du montant après frais ; un connecteur plus ancien pouvait retirer les frais deux fois en en modifiant une.

**Une correction qui change des montants fiscaux**

- **Les frais de réseau d’une dépense comptaient deux fois dans son gain.** Quand vous dépensiez des bitcoins (un Withdrawal de motif Spent) avec des frais de réseau en BTC, les frais comptaient comme une cession à part mais n’étaient pas déduits du produit de la dépense : le gain était trop élevé de la valeur des frais, en général quelques dollars. Versions 0.9.2 à 1.2.7, toutes les années fiscales ; cela ne donnait jamais que plus d’impôt, jamais moins. Que faire : Ledger Review, puis Recalculer le registre, comme ci-dessus. Corriger ou non une déclaration déjà déposée pour quelques dollars relève de vous ou de votre professionnel de la fiscalité.

**Confidentialité : un choix de prix fait sans demander (corrigé)**

- Qui a pu être concerné : de la 1.2.0 à la 1.2.7, ceux qui ont passé cette action à Décider plutôt dans BitcoinTX (auparavant Choisir dans BitcoinTX) après l’avoir mise sur Désactivé, Sites publics de prix ou Mon Mempool, ou qui ont lancé Définir les identifiants ou une commande à la main pendant ce réglage. BitcoinTX pouvait alors enregistrer Public price sites comme votre choix dans l’application sans demander, et s’en servir après le changement.
- Ce qui a pu être envoyé : des requêtes depuis l’adresse de votre serveur vers des sites publics, pour le prix du bitcoin (CoinGecko, Kraken, Bitstamp ou Coinbase) et la hauteur de bloc (Blockchain.info, Blockstream ou mempool.space). Jamais de dates, de montants ni rien de votre registre ; via Tor, pas même votre adresse.
- Que faire : confirmez ou changez le choix quand BitcoinTX le demande une fois après cette mise à jour (ci-dessus), ou vérifiez Settings > Privacy & Network.

**Nouveautés**

- **Des prix à l’heure.** Les valeurs que BitcoinTX remplit à partir du prix du BTC (une valeur de revenu ou de rebate laissée vide, le produit d’un Spent, la valeur de frais de réseau) utilisent désormais le prix au début de l’heure de la transaction : l’IRS évalue le bitcoin à la date et à l’heure. Quand votre choix autorise les sites publics de prix, BitcoinTX télécharge une fois les prix horaires de Bitstamp depuis 2013 (environ 3 Mo) et vérifie chaque année avec une empreinte fournie avec cette version. Rien de ce qui est déjà enregistré ne change : Ledger Review liste, par année fiscale, les valeurs au prix du jour que l’heure changerait, et ne change que celles que vous appliquez.
- **Un seul choix de prix.** Cette action propose désormais Mon Mempool sur ce serveur, Sites publics de prix, Personne ou Décider plutôt dans BitcoinTX, avec Tor et, pour Mempool, les sites publics en secours. Une nouvelle installation le demande avant de démarrer. Dans l’application, une seule carte de prix dit d’où viennent les prix et quand est arrivé le dernier, et le Dashboard, la barre latérale et le formulaire de transaction indiquent quel prix une valeur a utilisé. Coinbase et CoinGecko ne sont plus interrogés.
- **Bitcoins hérités.** Une nouvelle source de dépôt, Inherited : son coût d’acquisition est sa valeur à la date du décès, et toute vente de ces bitcoins est à long terme, marquée INHERITED sur le Form 8949.
- **Consolidations.** Un transfert au sein du même portefeuille (ou entre plateformes que BitcoinTX compte comme une seule) n’enregistre que ses frais de réseau, une cession de vos bitcoins les plus anciens.
- **Faire confiance à ce serveur.** Avec Décider plutôt dans BitcoinTX, un Mempool sur un autre serveur domestique à une adresse https peut être approuvé depuis la carte de prix.

**Sécurité et corrections mineures**

- D’un audit de sécurité : se déconnecter met fin à cette session partout ; les échecs de connexion des autres ne ralentissent plus un navigateur qui s’est déjà connecté ; une restauration rapporte les données d’une sauvegarde et garde l’identifiant, la clé IA et les réglages de prix de cette installation, ou ne change rien ; chaque requête a des limites de taille et de durée ; une modification ou suppression par le connecteur IA fait d’abord une copie de sauvegarde, et ses imports restent courts. Les détails seront publiés quand cette version sera disponible.
- Une modification ne peut plus enregistrer une valeur de frais négative, et un prix inférieur à un cent n’est jamais enregistré comme 0 $.

[Tout ce que contient la 1.2.8](${CHANGELOG})`,
  },
  migrations: {
    up: async ({ effects }) => {
      await storeJson.merge(effects, { recalculateLedger: true })
    },
    down: IMPOSSIBLE,
  },
})

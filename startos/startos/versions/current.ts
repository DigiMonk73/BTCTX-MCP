import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/main/docs/CHANGELOG.md'

/** 1.2.6:0: the 2026 report fixes (income values after edits, the date originally acquired, the Rebate source, the IRS forms' format, the preparer's page), one wallet stated plainly, the disclaimer; nothing for the package to migrate. */
export const current = VersionInfo.of({
  version: '1.2.6:0',
  releaseNotes: {
    en_US: `BitcoinTX 1.2.6 fixes what testing the 2026 forms turned up, and says plainly who BitcoinTX is for.

**Fixes that change tax figures**

- **Income deposits after an edit.** Changing an Income, Interest or Reward deposit's amount or date could keep its old value, and moving one from Bank to the Wallet or Exchange BTC with an AI assistant or the API could leave it at $0. A deposit of dollars (Bank, Exchange USD) marked Income, Interest or Reward that carried a value was counted as bitcoin income. All earlier versions, any tax year. What to do: open Settings > Ledger Review and fix each income deposit it lists: clear the value to use that day's price, or type the right one.
- **My BTC and Gift deposits keep their holding period.** They can now carry the date the coins were first acquired (by the giver, for a gift), so coins held more than a year count as long-term; before, the holding period started at the deposit. What to do: Ledger Review lists My BTC and Gift deposits without that date; add it where you know it.
- **Card sats-back is not income.** A new deposit source, Rebate, for bitcoin back for spending, such as a rewards card's sats-back: valued like income, its value when received is its cost basis, but it isn't counted as income. Entered as Reward, such bitcoin was counted as income, in every earlier version and tax year. What to do: change card or shopping rewards from Reward to Rebate (the value stays); keep mining, staking and bonuses as Reward; ask your tax professional if unsure.

**IRS forms and reports**

- Losses print in parentheses, as the IRS asks; tiny amounts print in full (0.00000005 BTC, not 5E-8); no more blank Form 8949 pages.
- The Complete Tax Report has a page for whoever files your return: what BitcoinTX fills on Form 8949 and Schedule D, what it leaves blank and why.
- Ledger Review lists income deposits with a $0 or blank value.

**One wallet, one exchange**

- BitcoinTX now states plainly that it's built for one self-custody wallet and one exchange account, and why: since 2025, IRS rules figure cost basis wallet by wallet.
- It also says it's software, not tax advice: check its figures with a tax professional before you file.

**Update your AI connector too**

- Using an AI assistant with BitcoinTX? In your AI app's configuration, change btctx-mcp==1.2.5 to btctx-mcp==1.2.6 (Connect an AI Assistant shows it) and restart the AI app. Your AI key stays the same. Otherwise the assistant keeps its old guide and enters card sats-back as Reward.

Coming from 1.2.4:0 or earlier? Set Login Credentials replaces Show Credentials and Reset Login Credentials; your login stays. Only if StartOS keeps no password for you, stop BitcoinTX and run Set Login Credentials before starting it again.

[Everything in 1.2.6](${CHANGELOG})`,
    es_ES: `BitcoinTX 1.2.6 corrige lo que encontraron las pruebas de los formularios de 2026 y dice claramente para quién es BitcoinTX.

**Correcciones que cambian cifras fiscales**

- **Depósitos de ingresos tras una edición.** Cambiar la cantidad o la fecha de un depósito Income, Interest o Reward podía conservar su valor anterior, y moverlo de Bank al Wallet o a Exchange BTC con un asistente de IA o la API podía dejarlo en 0 $. Un depósito en dólares (Bank, Exchange USD) marcado como Income, Interest o Reward que tenía un valor se contaba como ingreso en bitcoin. Todas las versiones anteriores, cualquier año fiscal. Qué hacer: abre Settings > Ledger Review y corrige cada depósito de ingresos que muestre: borra el valor para usar el precio de ese día o escribe el correcto.
- **Los depósitos My BTC y Gift conservan su periodo de tenencia.** Ahora pueden llevar la fecha en que se adquirieron las monedas por primera vez (por quien las regaló, en un regalo), así que las monedas mantenidas más de un año cuentan como largo plazo; antes, el periodo empezaba en el depósito. Qué hacer: Ledger Review muestra los depósitos My BTC y Gift sin esa fecha; añádela cuando la sepas.
- **El cashback en sats de una tarjeta no es un ingreso.** Un nuevo origen de depósito, Rebate, para el bitcoin que recibes por gastar, como el cashback en sats de una tarjeta de recompensas: se valora como un ingreso y su valor al recibirlo es su coste base, pero no cuenta como ingreso. Registrado como Reward, ese bitcoin se contaba como ingreso, en todas las versiones y años fiscales anteriores. Qué hacer: cambia las recompensas de tarjetas o compras de Reward a Rebate (el valor se conserva); deja la minería, el staking y los bonos como Reward; consulta a tu profesional fiscal si tienes dudas.

**Formularios del IRS e informes**

- Las pérdidas se imprimen entre paréntesis, como pide el IRS; las cantidades muy pequeñas se imprimen completas (0.00000005 BTC, no 5E-8); ya no hay páginas del Form 8949 en blanco.
- El Complete Tax Report tiene una página para quien presente tu declaración: qué rellena BitcoinTX en el Form 8949 y el Schedule D, qué deja en blanco y por qué.
- Ledger Review muestra los depósitos de ingresos con un valor de 0 $ o en blanco.

**Un monedero, un exchange**

- BitcoinTX ahora dice claramente que está hecho para un monedero de autocustodia y una cuenta en un exchange, y por qué: desde 2025, las normas del IRS calculan el coste base monedero por monedero.
- También dice que es software, no asesoramiento fiscal: revisa sus cifras con un profesional fiscal antes de presentar tu declaración.

**Actualiza también tu conector de IA**

- ¿Usas un asistente de IA con BitcoinTX? En la configuración de tu aplicación de IA, cambia btctx-mcp==1.2.5 por btctx-mcp==1.2.6 (Conectar un asistente de IA lo muestra) y reinicia la aplicación. Tu clave de IA no cambia. Si no, el asistente conserva su guía anterior y registra el cashback en sats como Reward.

¿Vienes de la 1.2.4:0 o anterior? Establecer credenciales de acceso sustituye a Mostrar credenciales y Restablecer credenciales de acceso; tu acceso se conserva. Solo si StartOS no guarda ninguna contraseña tuya, detén BitcoinTX y ejecuta Establecer credenciales de acceso antes de volver a iniciarlo.

[Todo lo de la 1.2.6](${CHANGELOG})`,
    de_DE: `BitcoinTX 1.2.6 behebt, was die Tests der Formulare für 2026 gefunden haben, und sagt klar, für wen BitcoinTX gedacht ist.

**Korrekturen, die Steuerzahlen ändern**

- **Einkommenseinzahlungen nach einer Änderung.** Wurde bei einer Einzahlung Income, Interest oder Reward der Betrag oder das Datum geändert, konnte ihr alter Wert bleiben, und wurde sie mit einem KI-Assistenten oder über die API von Bank in die Wallet oder nach Exchange BTC verschoben, konnte sie bei 0 $ landen. Eine Dollar-Einzahlung (Bank, Exchange USD), als Income, Interest oder Reward markiert und mit einem Wert, wurde als Bitcoin-Einkommen gezählt. Alle früheren Versionen, jedes Steuerjahr. Was zu tun ist: Öffne Settings > Ledger Review und korrigiere jede dort aufgeführte Einkommenseinzahlung: Lösche den Wert, um den Kurs des Tages zu verwenden, oder gib den richtigen ein.
- **My-BTC- und Gift-Einzahlungen behalten ihre Haltedauer.** Sie können jetzt das Datum tragen, an dem die Coins zuerst erworben wurden (bei einem Geschenk vom Schenkenden), sodass Coins, die länger als ein Jahr gehalten wurden, als langfristig gelten; bisher begann die Haltedauer mit der Einzahlung. Was zu tun ist: Ledger Review listet My-BTC- und Gift-Einzahlungen ohne dieses Datum auf; trage es ein, wo du es kennst.
- **Sats-Cashback einer Karte ist kein Einkommen.** Eine neue Einzahlungsquelle, Rebate, für Bitcoin, den du fürs Ausgeben zurückbekommst, etwa das Sats-Cashback einer Prämienkarte: bewertet wie Einkommen, sein Wert beim Erhalt sind seine Anschaffungskosten, aber er zählt nicht als Einkommen. Als Reward erfasst, wurde solcher Bitcoin als Einkommen gezählt, in jeder früheren Version und jedem Steuerjahr. Was zu tun ist: Stelle Karten- oder Einkaufsprämien von Reward auf Rebate um (der Wert bleibt); Mining, Staking und Boni bleiben Reward; frag im Zweifel deinen Steuerberater.

**IRS-Formulare und Berichte**

- Verluste stehen in Klammern, wie der IRS es verlangt; winzige Beträge stehen vollständig da (0.00000005 BTC, nicht 5E-8); keine leeren Seiten des Form 8949 mehr.
- Der Complete Tax Report hat eine Seite für die Person, die deine Erklärung einreicht: was BitcoinTX in Form 8949 und Schedule D ausfüllt, was es leer lässt und warum.
- Ledger Review listet Einkommenseinzahlungen mit einem Wert von 0 $ oder ohne Wert auf.

**Eine Wallet, eine Börse**

- BitcoinTX sagt jetzt klar, dass es für eine Self-Custody-Wallet und ein Börsenkonto gebaut ist, und warum: Seit 2025 ermitteln die IRS-Regeln die Anschaffungskosten Wallet für Wallet.
- Es sagt auch, dass es Software ist, keine Steuerberatung: Lass seine Zahlen vor der Abgabe von einem Steuerberater prüfen.

**Aktualisiere auch deinen KI-Connector**

- Nutzt du einen KI-Assistenten mit BitcoinTX? Ändere in der Konfiguration deiner KI-App btctx-mcp==1.2.5 in btctx-mcp==1.2.6 (KI-Assistenten verbinden zeigt es an) und starte die App neu. Dein KI-Schlüssel bleibt gleich. Sonst behält der Assistent seinen alten Leitfaden und erfasst Sats-Cashback als Reward.

Du kommst von 1.2.4:0 oder älter? Zugangsdaten festlegen ersetzt Zugangsdaten anzeigen und Zugangsdaten zurücksetzen; deine Zugangsdaten bleiben. Nur wenn StartOS kein Passwort für dich gespeichert hat, stoppe BitcoinTX und führe Zugangsdaten festlegen vor dem nächsten Start aus.

[Alles in 1.2.6](${CHANGELOG})`,
    pl_PL: `BitcoinTX 1.2.6 poprawia to, co wykryły testy formularzy na 2026 rok, i jasno mówi, dla kogo jest BitcoinTX.

**Poprawki, które zmieniają wartości podatkowe**

- **Wpłaty dochodu po edycji.** Zmiana kwoty lub daty wpłaty Income, Interest lub Reward mogła zachować jej poprzednią wartość, a przeniesienie jej z Bank do Wallet lub Exchange BTC przez asystenta AI lub API mogło zostawić ją na 0 $. Wpłata dolarów (Bank, Exchange USD) oznaczona jako Income, Interest lub Reward, która miała wartość, była liczona jako dochód w bitcoinach. Wszystkie wcześniejsze wersje, każdy rok podatkowy. Co zrobić: otwórz Settings > Ledger Review i popraw każdą wpłatę dochodu, którą pokazuje: wyczyść wartość, aby użyć ceny z tego dnia, albo wpisz właściwą.
- **Wpłaty My BTC i Gift zachowują okres posiadania.** Mogą teraz mieć datę pierwszego nabycia monet (w przypadku prezentu przez darczyńcę), więc monety trzymane dłużej niż rok liczą się jako długoterminowe; wcześniej okres posiadania zaczynał się od wpłaty. Co zrobić: Ledger Review pokazuje wpłaty My BTC i Gift bez tej daty; dodaj ją tam, gdzie ją znasz.
- **Cashback w satoshi z karty nie jest dochodem.** Nowe źródło wpłaty, Rebate, dla bitcoina otrzymanego za wydatki, np. cashbacku w satoshi z karty nagród: wyceniany jak dochód, jego wartość w chwili otrzymania jest kosztem nabycia, ale nie liczy się jako dochód. Wpisany jako Reward, taki bitcoin był liczony jako dochód we wszystkich wcześniejszych wersjach i latach podatkowych. Co zrobić: zmień nagrody z kart i zakupów z Reward na Rebate (wartość zostaje); kopanie, staking i bonusy zostaw jako Reward; w razie wątpliwości zapytaj doradcę podatkowego.

**Formularze IRS i raporty**

- Straty drukują się w nawiasach, jak wymaga IRS; bardzo małe kwoty drukują się w całości (0.00000005 BTC, nie 5E-8); koniec z pustymi stronami Form 8949.
- Complete Tax Report ma stronę dla osoby składającej Twoje zeznanie: co BitcoinTX wypełnia w Form 8949 i Schedule D, co zostawia puste i dlaczego.
- Ledger Review pokazuje wpłaty dochodu z wartością 0 $ lub bez wartości.

**Jeden portfel, jedna giełda**

- BitcoinTX teraz jasno mówi, że jest stworzony dla jednego portfela niekustodialnego i jednego konta na giełdzie, i dlaczego: od 2025 r. przepisy IRS ustalają koszt nabycia osobno dla każdego portfela.
- Mówi też, że jest oprogramowaniem, a nie poradą podatkową: przed złożeniem zeznania sprawdź jego wyliczenia z doradcą podatkowym.

**Zaktualizuj też łącznik AI**

- Używasz asystenta AI z BitcoinTX? W konfiguracji aplikacji AI zmień btctx-mcp==1.2.5 na btctx-mcp==1.2.6 (pokazuje to Połącz asystenta AI) i uruchom aplikację ponownie. Twój klucz AI się nie zmienia. W przeciwnym razie asystent zachowa stary przewodnik i będzie wpisywał cashback w satoshi jako Reward.

Aktualizujesz z 1.2.4:0 lub starszej wersji? Ustaw dane logowania zastępuje Pokaż dane logowania i Zresetuj dane logowania; Twoje dane logowania zostają. Tylko jeśli StartOS nie przechowuje dla Ciebie hasła, zatrzymaj BitcoinTX i uruchom Ustaw dane logowania przed ponownym uruchomieniem.

[Wszystko w 1.2.6](${CHANGELOG})`,
    fr_FR: `BitcoinTX 1.2.6 corrige ce que les tests des formulaires de 2026 ont révélé, et dit clairement à qui BitcoinTX s’adresse.

**Corrections qui changent des montants fiscaux**

- **Dépôts de revenus après une modification.** Changer le montant ou la date d’un dépôt Income, Interest ou Reward pouvait conserver son ancienne valeur, et le déplacer de Bank vers Wallet ou Exchange BTC avec un assistant IA ou l’API pouvait le laisser à 0 $. Un dépôt en dollars (Bank, Exchange USD) marqué Income, Interest ou Reward et portant une valeur était compté comme un revenu en bitcoin. Toutes les versions antérieures, toute année fiscale. Que faire : ouvrez Settings > Ledger Review et corrigez chaque dépôt de revenus qu’il liste : effacez la valeur pour utiliser le prix de ce jour-là, ou saisissez la bonne.
- **Les dépôts My BTC et Gift gardent leur durée de détention.** Ils peuvent désormais porter la date d’acquisition initiale des bitcoins (par le donateur, pour un don), si bien que des bitcoins détenus plus d’un an comptent à long terme ; auparavant, la durée de détention partait du dépôt. Que faire : Ledger Review liste les dépôts My BTC et Gift sans cette date ; ajoutez-la quand vous la connaissez.
- **Le cashback en sats d’une carte n’est pas un revenu.** Une nouvelle source de dépôt, Rebate, pour les bitcoins reçus en retour de vos dépenses, comme le cashback en sats d’une carte de récompenses : évaluée comme un revenu, sa valeur à la réception est son coût d’acquisition, mais elle ne compte pas comme un revenu. Saisis comme Reward, ces bitcoins étaient comptés comme un revenu, dans toutes les versions et années fiscales antérieures. Que faire : passez les récompenses de carte ou d’achats de Reward à Rebate (la valeur reste) ; gardez le minage, le staking et les bonus en Reward ; en cas de doute, demandez à votre professionnel de la fiscalité.

**Formulaires de l’IRS et rapports**

- Les pertes s’impriment entre parenthèses, comme le demande l’IRS ; les très petits montants s’impriment en entier (0.00000005 BTC, pas 5E-8) ; plus de pages vides du Form 8949.
- Le Complete Tax Report a une page pour la personne qui dépose votre déclaration : ce que BitcoinTX remplit sur le Form 8949 et le Schedule D, ce qu’il laisse vide et pourquoi.
- Ledger Review liste les dépôts de revenus dont la valeur est de 0 $ ou vide.

**Un portefeuille, une plateforme**

- BitcoinTX dit désormais clairement qu’il est conçu pour un portefeuille en auto-garde et un compte sur une plateforme d’échange, et pourquoi : depuis 2025, les règles de l’IRS calculent le coût d’acquisition portefeuille par portefeuille.
- Il dit aussi qu’il est un logiciel, pas un conseil fiscal : faites vérifier ses chiffres par un professionnel de la fiscalité avant de déclarer.

**Mettez aussi à jour votre connecteur IA**

- Vous utilisez un assistant IA avec BitcoinTX ? Dans la configuration de votre application d’IA, remplacez btctx-mcp==1.2.5 par btctx-mcp==1.2.6 (Connecter un assistant IA l’affiche) et redémarrez l’application. Votre clé IA reste la même. Sinon, l’assistant garde son ancien guide et saisit le cashback en sats comme Reward.

Vous venez de la 1.2.4:0 ou d’une version antérieure ? Définir les identifiants remplace Afficher les identifiants et Réinitialiser les identifiants ; vos identifiants sont conservés. Seulement si StartOS ne garde aucun mot de passe pour vous, arrêtez BitcoinTX et lancez Définir les identifiants avant de le redémarrer.

[Tout ce que contient la 1.2.6](${CHANGELOG})`,
  },
  migrations: {
    up: async () => {},
    down: IMPOSSIBLE,
  },
})

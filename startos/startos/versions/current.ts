import { IMPOSSIBLE, VersionInfo } from '@start9labs/start-sdk'

const CHANGELOG =
  'https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.3/docs/CHANGELOG.md'

/**
 * 2.0.3:0, the third maintenance update of 2.0. 2.0.2:0's migration was
 * empty, so it is bumped in place (Start9's versions.md), with no migration of
 * its own. The notes cover what changed since 2.0.2:0, which the community
 * registry serves: what to do after updating, that 2026's IRS forms are still
 * the drafts, each tax-figures fix with what the user saw, which tax years
 * and what to do, the other fixes and the known issues. Start9's rule: what a
 * user observes, never how it was done, and never the minimum StartOS; ours:
 * never which BitcoinTX versions had a bug (startos/AGENTS.md).
 */
export const current = VersionInfo.of({
  version: '2.0.3:0',
  releaseNotes: {
    en_US: `BitcoinTX 2.0.3 is a maintenance update. It fixes eight bugs that could make a tax figure wrong (below, each with who could be affected and what to do), shows the coins a sale uses before you save it, and fixes a few smaller bugs. Its 2026 IRS forms are still the IRS's drafts.

**Before you update**

- **Coming from a version older than 2.0.2?** Read the notes of the versions in between first: [2.0.2's](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.2/docs/CHANGELOG.md) and [2.0.1's](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.1/docs/CHANGELOG.md) timezone fixes can ask you to correct some times. From 1.x, also [2.0.0's](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0): 2.0 changes how your ledger is stored, and StartOS can't undo it by itself, so make a StartOS backup of BitcoinTX and keep it, as it's your way back to 1.x.

**What to do after updating**

- **Reload any BitcoinTX page left open** in a browser.
- **If you use an AI connector**, update it: in your AI app's configuration, change the version after btctx-mcp== to 2.0.3, as Settings > Connect an AI Assistant gives it, then restart the AI app.
- Then see the fixes below: most ledgers need nothing more.

**The 2026 IRS forms**

- The IRS hasn't published the final 2026 Form 8949 and Schedule D yet. Until 31 December, Reports offers 2026's forms as a preview: the IRS's drafts, marked DRAFT — DO NOT FILE. Don't file them. A later update brings the final forms; from 1 January, Reports asks for that update. The Complete Tax Report and Transaction History work for any year.

**New**

- **The Sell form shows the coins a sale uses**, oldest first, before you save it and when you open a saved one: each lot's date acquired, amount and cost, and the proceeds, gain and term it will have on Form 8949. A withdrawal from an exchange lists its coins too. Nothing is computed differently.
- **Changing a deposit valued from the price** (income, interest, a reward, a rebate, an inheritance) to My BTC, Gift or N/A now asks for what the coins cost, as a new deposit of those sources does. A deposit changed this way before keeps its value: if it's your own coins or a gift, check that its cost basis is what was paid.

**Fixes that can change a figure**

- **Coins acquired on 28 February and sold on 29 February of the next year** were reported long-term, but they're short-term. The gain stays the same; the sale moves from Form 8949's Part II to Part I, and on Schedule D. This touches only a sale, spend, donation or network fee on 29 February 2012, 2016, 2020 or 2024 of coins acquired on 28 February of the year before.
  - **What to do:** if you have such a disposal, run Recalculate Ledger (Settings > Account) and print that year's forms again. If you already filed that year with it as long-term, ask your tax preparer whether to amend.
- **Rows that share a time, entered by the AI connector,** were put in an order by type (deposits, buys, transfers, sales, withdrawals) instead of the order given, so a sale and a move at the same time could take other coins than the same rows imported from a file: another cost basis, gain and holding period, in any tax year. That's likely when the AI enters rows by date alone, which it puts at noon.
  - **What to do:** update the AI connector (above). If an AI entered, in one request, rows of different types on the same account at the same time (or on the same day without a time), check the cost basis and term of the sales, spends and moves out of those accounts from that day on against your records. Where one took other coins than it should have, put the rows in their real order by editing a time (a minute apart is enough).
- **A time typed in the transaction form, on a device with old timezone data,** could be saved an hour off:
  - British Columbia, Alberta, Manitoba, the Northwest Territories and Cuba, from 1 November 2026: an hour late;
  - Morocco, from 20 September 2026: an hour early;
  - Moldova: only a time from 03:00 to 04:00 on the last Sunday of March (an hour early) or of October (an hour late);
  - on a device with data from 2024 or earlier, also Paraguay, from 23 March to 5 October 2025 and from 22 March to 4 October 2026: an hour late; with data from 2023 or earlier, also Kazakhstan (Almaty's and Kostanay's time), from 1 March 2024: an hour early.

  That moved the hour's price BitcoinTX fills in, and near midnight the date: Form 8949's date, the holding period and, on 31 December, the tax year. BitcoinTX now works out the moment by its own timezone rules; on an out-of-date device the form says the time will show an hour off until the device is updated.
  - **What to do:** if you typed transactions on a device that may have been out of date, in one of those places and periods, update the device first. Then open each such transaction and compare its time with the receipt you typed it from; where it's an hour off, type the receipt's time again.
- **A bitcoin amount written with a comma in a file** ("1,234", or "2,500" from a spreadsheet that writes decimals with a comma) was read as a thousand times as much by BitcoinTX's own CSV import and River's, in any tax year. Such an amount is now refused, saying to write decimals with a point; dollars keep their thousands separator.
  - **What to do:** if you imported a file from a spreadsheet, look for a bitcoin amount a thousand times too large: the Dashboard's holdings would show it at once.
- **A file with a stray quote (") lost rows without a word,** in BitcoinTX's own CSV import, River's and every other exchange's: the rows after a quote never closed, or between two stray quotes, vanished, and the row holding the quote could take a later row's text. Such a file is now refused, saying what was found, and so is a file with a cell over more than one line, naming its row and column. Only a hand-edited or damaged file has a stray quote.
  - **What to do:** if you imported a file you had edited by hand, compare the number of transactions the import saved with the file's rows, add any missing one, and check the transaction just before them (its note, its date acquired and, for River's file, its type).
- **A deposit's typed value was kept when its source changed.** A cost typed for My BTC, Gift or N/A was kept as the value when the deposit was changed to income, interest, a reward, a rebate or an inheritance; and, through the AI connector, an inheritance's value was kept when the deposit was changed to income, or income's when changed to Inherited, though the two are taken on different dates. That could put a wrong income or basis in the deposit's tax year. Such a change now values the deposit again from the price (an inheritance at its date of death), unless another value is given with it.
  - **What to do:** if you changed a deposit like that, open it and clear Cost Basis to have it valued again from the price.

**Other fixes** (no figure changes)

- Ledger Review's advice for a value left blank or $0 says to type the value when BitcoinTX asks no one for prices, or when only your own Mempool, not installed yet or without its backup, could price it, instead of saying to clear it.
- A CSV file saved as an old Mac's "CSV (Macintosh)" now imports.
- The Instructions say how to keep BitcoinTX's login cookie to BitcoinTX when other services are opened at the same address, and Set Login Credentials says what a new password leaves valid: every browser is signed out, and an AI key keeps working.
- **Security:** BitcoinTX includes the latest security fixes of the software it's built on.

**Known issues**

- Only on a ledger holding a row whose value is blank in the database (blanked by hand, or left by an old version in a ledger not recalculated since), a save can need a second try, and a value dated after the price history's last hour can take the day's price, marked, instead of the hour's. Ledger Review lists such a value, and you can apply the hour's price there.
- BitcoinTX can't yet match a Form 1099-DA that lists a transfer's or a gift's network fee, or a fee without its withdrawal, on Form 8949: the Complete Tax Report says how to correct it by hand.
- BitcoinTX's own CSV import reads some hand-made files without a word: a column named twice takes its last value, a time that a clock change skips or repeats is read as one moment without a note, and a date such as 05/03/2024 is read month first. Check the preview's rows against your file; BitcoinTX's own export writes none of these.

[Everything in 2.0.3](${CHANGELOG})`,
    es_ES: `BitcoinTX 2.0.3 es una actualización de mantenimiento. Corrige ocho errores que podían hacer incorrecta una cifra fiscal (abajo, cada uno con a quién puede afectar y qué hacer), muestra las monedas que usa una venta antes de guardarla y corrige algunos errores menores. Sus formularios del IRS de 2026 siguen siendo los borradores del IRS.

**Antes de actualizar**

- **¿Vienes de una versión anterior a la 2.0.2?** Lee antes las notas de las versiones intermedias: las correcciones horarias de [la 2.0.2](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.2/docs/CHANGELOG.md) y de [la 2.0.1](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.1/docs/CHANGELOG.md) pueden pedirte que corrijas algunas horas. Desde la 1.x, también [las de la 2.0.0](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0): la 2.0 cambia cómo se guarda tu libro contable, y StartOS no puede deshacerlo por sí solo, así que haz una copia de seguridad de BitcoinTX en StartOS y guárdala, porque es tu forma de volver a la 1.x.

**Después de actualizar**

- **Vuelve a cargar cualquier página de BitcoinTX que haya quedado abierta** en un navegador.
- **Si usas un conector de IA**, actualízalo: en la configuración de tu aplicación de IA, cambia la versión que sigue a btctx-mcp== por 2.0.3, como la da Settings > Connect an AI Assistant, y reinicia la aplicación de IA.
- Después mira las correcciones de abajo: la mayoría de los libros contables no necesitan nada más.

**Los formularios del IRS de 2026**

- El IRS aún no ha publicado el formulario 8949 ni el Schedule D definitivos de 2026. Hasta el 31 de diciembre, Reports ofrece los de 2026 como vista previa: los borradores del IRS, marcados DRAFT — DO NOT FILE. No los presentes. Una actualización posterior trae los formularios definitivos; desde el 1 de enero, Reports pide esa actualización. El Complete Tax Report y el Transaction History funcionan para cualquier año.

**Novedades**

- **El formulario Sell muestra las monedas que usa una venta**, de la más antigua a la más reciente, antes de guardarla y al abrir una ya guardada: la fecha de adquisición, la cantidad y el coste de cada lote, y los ingresos, la ganancia y el plazo que tendrá en el formulario 8949. Una retirada de un exchange también muestra sus monedas. Nada se calcula de otra forma.
- **Cambiar un depósito valorado a partir del precio** (ingreso, intereses, una recompensa, un reembolso, una herencia) a My BTC, Gift o N/A ahora pide lo que costaron las monedas, como lo hace un depósito nuevo de esos orígenes. Un depósito cambiado así antes mantiene su valor: si son tus propias monedas o un regalo, comprueba que su base de coste es lo que se pagó.

**Correcciones que pueden cambiar una cifra**

- **Unas monedas adquiridas el 28 de febrero y vendidas el 29 de febrero del año siguiente** se declaraban a largo plazo, pero son a corto plazo. La ganancia no cambia; la venta pasa de la parte II a la parte I del formulario 8949, y en el Schedule D. Solo afecta a una venta, un gasto, una donación o una comisión de red del 29 de febrero de 2012, 2016, 2020 o 2024 de monedas adquiridas el 28 de febrero del año anterior.
  - **Qué hacer:** si tienes una disposición así, ejecuta Recalculate Ledger (Settings > Account) y vuelve a imprimir los formularios de ese año. Si ya presentaste ese año con ella a largo plazo, pregunta a tu asesor fiscal si debes presentar una declaración rectificativa.
- **Las filas que comparten una hora, añadidas por el conector de IA,** se ordenaban por tipo (depósitos, compras, transferencias, ventas, retiradas) en lugar de en el orden dado, así que una venta y un movimiento a la misma hora podían tomar otras monedas que las mismas filas importadas desde un archivo: otra base de coste, otra ganancia y otro periodo de tenencia, en cualquier año fiscal. Es probable cuando la IA añade filas solo con una fecha, que pone a mediodía.
  - **Qué hacer:** actualiza el conector de IA (arriba). Si una IA añadió, en una sola petición, filas de distintos tipos en la misma cuenta a la misma hora (o el mismo día sin hora), compara con tus registros la base de coste y el plazo de las ventas, los gastos y los movimientos de salida de esas cuentas desde ese día. Donde una tomó otras monedas de las que debía, pon las filas en su orden real editando una hora (basta un minuto de diferencia).
- **Una hora escrita en el formulario de transacción, en un dispositivo con datos de zona horaria antiguos,** podía guardarse con una hora de diferencia:
  - Columbia Británica, Alberta, Manitoba, los Territorios del Noroeste y Cuba, desde el 1 de noviembre de 2026: una hora tarde;
  - Marruecos, desde el 20 de septiembre de 2026: una hora antes;
  - Moldavia: solo un momento entre las 03:00 y las 04:00 del último domingo de marzo (una hora antes) o de octubre (una hora tarde);
  - en un dispositivo con datos de 2024 o anteriores, también Paraguay, del 23 de marzo al 5 de octubre de 2025 y del 22 de marzo al 4 de octubre de 2026: una hora tarde; con datos de 2023 o anteriores, también Kazajistán (la hora de Almaty y de Kostanái), desde el 1 de marzo de 2024: una hora antes.

  Eso cambiaba el precio de la hora que rellena BitcoinTX y, cerca de la medianoche, la fecha: la fecha del formulario 8949, el periodo de tenencia y, el 31 de diciembre, el año fiscal. BitcoinTX calcula ahora el momento con sus propias reglas horarias; en un dispositivo desactualizado, el formulario avisa de que la hora se mostrará con una hora de diferencia hasta que se actualice el dispositivo.
  - **Qué hacer:** si escribiste transacciones en un dispositivo que podía estar desactualizado, en uno de esos lugares y periodos, actualiza primero el dispositivo. Después abre cada una de esas transacciones y compara su hora con el recibo del que la copiaste; si hay una hora de diferencia, vuelve a escribir la hora del recibo.
- **Una cantidad de bitcoin escrita con coma en un archivo** ("1,234", o "2,500" desde una hoja de cálculo que escribe los decimales con coma) se leía como mil veces más en la importación CSV propia de BitcoinTX y en la de River, en cualquier año fiscal. Una cantidad así se rechaza ahora, indicando que se escriban los decimales con punto; los dólares mantienen su separador de miles.
  - **Qué hacer:** si importaste un archivo desde una hoja de cálculo, busca una cantidad de bitcoin mil veces demasiado grande: los saldos del Dashboard la mostrarían enseguida.
- **Un archivo con unas comillas (") sueltas perdía filas sin avisar,** en la importación CSV propia de BitcoinTX, en la de River y en la de cualquier otro exchange: las filas tras unas comillas nunca cerradas, o entre dos comillas sueltas, desaparecían, y la fila con las comillas podía tomar el texto de una fila posterior. Un archivo así se rechaza ahora, diciendo qué se encontró, y también uno con una celda en más de una línea, indicando su fila y su columna. Solo un archivo editado a mano o dañado tiene comillas sueltas.
  - **Qué hacer:** si importaste un archivo que habías editado a mano, compara el número de transacciones que guardó la importación con las filas del archivo, añade la que falte y revisa la transacción justo anterior (su nota, su fecha de adquisición y, en el archivo de River, su tipo).
- **El valor escrito de un depósito se mantenía al cambiar su origen.** Un coste escrito para My BTC, Gift o N/A se mantenía como valor al cambiar el depósito a ingreso, intereses, una recompensa, un reembolso o una herencia; y, a través del conector de IA, el valor de una herencia se mantenía al cambiar el depósito a ingreso, o el de un ingreso al cambiarlo a Inherited, aunque los dos se toman en fechas distintas. Eso podía poner un ingreso o una base incorrectos en el año fiscal del depósito. Un cambio así valora ahora el depósito de nuevo a partir del precio (una herencia, en su fecha de fallecimiento), salvo que se dé otro valor con él.
  - **Qué hacer:** si cambiaste un depósito así, ábrelo y vacía Cost Basis para que se valore de nuevo a partir del precio.

**Otras correcciones** (ninguna cifra cambia)

- El consejo de Ledger Review para un valor vacío o de $0 dice que escribas el valor cuando BitcoinTX no pide precios a nadie, o cuando solo tu propio Mempool, aún sin instalar o sin su respaldo, podría dar el precio, en lugar de decir que lo vacíes.
- Un archivo CSV guardado como "CSV (Macintosh)" de un Mac antiguo ahora se importa.
- Las instrucciones dicen cómo mantener la cookie de inicio de sesión de BitcoinTX solo para BitcoinTX cuando otros servicios se abren en la misma dirección, y Set Login Credentials dice qué deja válido una contraseña nueva: se cierra la sesión en todos los navegadores, y una clave de IA sigue funcionando.
- **Seguridad:** BitcoinTX incluye las últimas correcciones de seguridad del software sobre el que está construido.

**Problemas conocidos**

- Solo en un libro contable con una fila cuyo valor está vacío en la base de datos (vaciado a mano, o dejado por una versión antigua en un libro contable no recalculado desde entonces), un guardado puede necesitar un segundo intento, y un valor con fecha posterior a la última hora del historial de precios puede tomar el precio del día, marcado, en lugar del de la hora. Ledger Review muestra un valor así, y allí puedes aplicar el precio de la hora.
- BitcoinTX aún no puede cuadrar en el formulario 8949 un Form 1099-DA que incluya la comisión de red de una transferencia o de un regalo, o una comisión sin su retirada: el Complete Tax Report dice cómo corregirlo a mano.
- La importación CSV propia de BitcoinTX lee sin avisar algunos archivos hechos a mano: una columna con el mismo nombre dos veces toma su último valor, una hora que un cambio de hora salta o repite se lee como un solo momento sin ninguna nota, y una fecha como 05/03/2024 se lee con el mes primero. Compara las filas de la vista previa con tu archivo; la exportación propia de BitcoinTX no escribe ninguna de estas.

[Todo lo que trae la 2.0.3](${CHANGELOG})`,
    de_DE: `BitcoinTX 2.0.3 ist ein Wartungsupdate. Es behebt acht Fehler, die eine Steuerzahl falsch machen konnten (unten, jeweils mit Angaben dazu, wen es betreffen kann und was zu tun ist), zeigt die Coins, die ein Verkauf nutzt, bevor du ihn speicherst, und behebt einige kleinere Fehler. Seine IRS-Formulare für 2026 sind noch die Entwürfe des IRS.

**Vor dem Update**

- **Du kommst von einer Version vor 2.0.2?** Lies zuerst die Hinweise der Versionen dazwischen: Die Zeitzonen-Korrekturen von [2.0.2](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.2/docs/CHANGELOG.md) und [2.0.1](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.1/docs/CHANGELOG.md) können dich bitten, einige Uhrzeiten zu korrigieren. Von 1.x aus auch [die Hinweise zu 2.0.0](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0): 2.0 ändert, wie dein Journal gespeichert wird, und StartOS kann das nicht von selbst rückgängig machen. Erstelle also eine StartOS-Sicherung von BitcoinTX und bewahre sie auf, denn sie ist dein Weg zurück zu 1.x.

**Nach dem Update**

- **Lade jede in einem Browser offen gebliebene Seite von BitcoinTX neu.**
- **Wenn du einen KI-Connector nutzt**, aktualisiere ihn: Ändere in der Konfiguration deiner KI-App die Version nach btctx-mcp== in 2.0.3, wie Settings > Connect an AI Assistant sie angibt, und starte die KI-App neu.
- Dann sieh dir die Korrekturen unten an: Die meisten Journale brauchen nichts weiter.

**Die IRS-Formulare für 2026**

- Der IRS hat das endgültige Formular 8949 und den endgültigen Schedule D für 2026 noch nicht veröffentlicht. Bis zum 31. Dezember bietet Reports die Formulare für 2026 als Vorschau an: die Entwürfe des IRS, markiert mit DRAFT — DO NOT FILE. Reiche sie nicht ein. Ein späteres Update bringt die endgültigen Formulare; ab dem 1. Januar bittet Reports um dieses Update. Der Complete Tax Report und die Transaction History funktionieren für jedes Jahr.

**Neu**

- **Das Formular Sell zeigt die Coins, die ein Verkauf nutzt**, die ältesten zuerst, bevor du ihn speicherst und wenn du einen gespeicherten öffnest: Erwerbsdatum, Menge und Kosten jedes Lots sowie Erlös, Gewinn und Frist, die er auf Formular 8949 haben wird. Eine Auszahlung von einer Börse zeigt ihre Coins ebenfalls. Nichts wird anders berechnet.
- **Eine aus dem Preis bewertete Einzahlung** (Einkommen, Zinsen, eine Belohnung, ein Rabatt, ein Erbe) auf My BTC, Gift oder N/A zu ändern, fragt jetzt nach den Kosten der Coins, wie es eine neue Einzahlung dieser Herkunft tut. Eine früher so geänderte Einzahlung behält ihren Wert: Sind es deine eigenen Coins oder ein Geschenk, prüfe, ob ihre Kostenbasis das Bezahlte ist.

**Korrekturen, die eine Zahl ändern können**

- **Coins, die am 28. Februar erworben und am 29. Februar des nächsten Jahres verkauft wurden,** wurden als langfristig ausgewiesen, sind aber kurzfristig. Der Gewinn bleibt gleich; der Verkauf wandert von Teil II in Teil I von Formular 8949 und auf Schedule D. Das betrifft nur einen Verkauf, eine Ausgabe, eine Spende oder eine Netzwerkgebühr am 29. Februar 2012, 2016, 2020 oder 2024 von Coins, die am 28. Februar des Vorjahres erworben wurden.
  - **Was zu tun ist:** Hast du eine solche Veräußerung, führe Recalculate Ledger aus (Settings > Account) und drucke die Formulare dieses Jahres erneut. Hast du dieses Jahr schon mit ihr als langfristig eingereicht, frage deinen Steuerberater, ob du eine berichtigte Erklärung abgeben solltest.
- **Zeilen mit derselben Uhrzeit, vom KI-Connector eingetragen,** wurden nach Typ geordnet (Einzahlungen, Käufe, Transfers, Verkäufe, Auszahlungen) statt in der angegebenen Reihenfolge, sodass ein Verkauf und eine Übertragung zur selben Uhrzeit andere Coins nehmen konnten als dieselben Zeilen aus einer importierten Datei: eine andere Kostenbasis, ein anderer Gewinn und eine andere Haltedauer, in jedem Steuerjahr. Das ist wahrscheinlich, wenn die KI Zeilen nur mit einem Datum einträgt, die sie auf Mittag legt.
  - **Was zu tun ist:** Aktualisiere den KI-Connector (oben). Hat eine KI in einer Anfrage Zeilen verschiedener Typen auf demselben Konto zur selben Uhrzeit eingetragen (oder am selben Tag ohne Uhrzeit), prüfe Kostenbasis und Frist der Verkäufe, Ausgaben und Übertragungen aus diesen Konten ab diesem Tag anhand deiner Unterlagen. Wo eine andere Coins genommen hat als sie sollte, bringe die Zeilen in ihre echte Reihenfolge, indem du eine Uhrzeit änderst (eine Minute Abstand genügt).
- **Eine im Transaktionsformular eingegebene Uhrzeit, auf einem Gerät mit alten Zeitzonendaten,** konnte um eine Stunde verschoben gespeichert werden:
  - British Columbia, Alberta, Manitoba, die Nordwest-Territorien und Kuba, ab dem 1. November 2026: eine Stunde zu spät;
  - Marokko, ab dem 20. September 2026: eine Stunde zu früh;
  - Moldau: nur eine Uhrzeit von 03:00 bis 04:00 am letzten Sonntag im März (eine Stunde zu früh) oder im Oktober (eine Stunde zu spät);
  - auf einem Gerät mit Daten von 2024 oder älter auch Paraguay, vom 23. März bis 5. Oktober 2025 und vom 22. März bis 4. Oktober 2026: eine Stunde zu spät; mit Daten von 2023 oder älter auch Kasachstan (die Zeit von Almaty und Kostanai), ab dem 1. März 2024: eine Stunde zu früh.

  Das verschob den Stundenpreis, den BitcoinTX ausfüllt, und nahe Mitternacht das Datum: das Datum auf Formular 8949, die Haltedauer und am 31. Dezember das Steuerjahr. BitcoinTX berechnet den Zeitpunkt jetzt nach seinen eigenen Zeitzonenregeln; auf einem veralteten Gerät sagt das Formular, dass die Uhrzeit um eine Stunde verschoben angezeigt wird, bis das Gerät aktualisiert ist.
  - **Was zu tun ist:** Hast du Transaktionen auf einem Gerät eingegeben, das veraltet gewesen sein kann, an einem dieser Orte und in einem dieser Zeiträume, aktualisiere zuerst das Gerät. Öffne dann jede solche Transaktion und vergleiche ihre Uhrzeit mit dem Beleg, aus dem du sie abgetippt hast; weicht sie um eine Stunde ab, gib die Uhrzeit des Belegs erneut ein.
- **Ein mit Komma geschriebener Bitcoin-Betrag in einer Datei** ("1,234", oder "2,500" aus einer Tabellenkalkulation, die Dezimalstellen mit Komma schreibt) wurde vom eigenen CSV-Import von BitcoinTX und dem von River als das Tausendfache gelesen, in jedem Steuerjahr. Ein solcher Betrag wird jetzt abgelehnt, mit dem Hinweis, Dezimalstellen mit Punkt zu schreiben; Dollarbeträge behalten ihr Tausendertrennzeichen.
  - **Was zu tun ist:** Hast du eine Datei aus einer Tabellenkalkulation importiert, suche nach einem Bitcoin-Betrag, der tausendmal zu groß ist: Die Bestände im Dashboard würden ihn sofort zeigen.
- **Eine Datei mit einem verirrten Anführungszeichen (") verlor ohne Meldung Zeilen,** im eigenen CSV-Import von BitcoinTX, in dem von River und in dem jeder anderen Börse: Die Zeilen nach einem nie geschlossenen Anführungszeichen oder zwischen zwei verirrten verschwanden, und die Zeile mit dem Anführungszeichen konnte den Text einer späteren Zeile übernehmen. Eine solche Datei wird jetzt abgelehnt, mit Angabe des Gefundenen, ebenso eine Datei mit einer Zelle über mehr als eine Zeile, mit Angabe ihrer Zeile und Spalte. Nur eine von Hand bearbeitete oder beschädigte Datei hat ein verirrtes Anführungszeichen.
  - **Was zu tun ist:** Hast du eine von Hand bearbeitete Datei importiert, vergleiche die Zahl der vom Import gespeicherten Transaktionen mit den Zeilen der Datei, füge jede fehlende hinzu und prüfe die Transaktion direkt davor (ihre Notiz, ihr Erwerbsdatum und bei der Datei von River ihren Typ).
- **Der eingegebene Wert einer Einzahlung blieb erhalten, wenn ihre Herkunft geändert wurde.** Für My BTC, Gift oder N/A eingegebene Kosten blieben als Wert erhalten, wenn die Einzahlung auf Einkommen, Zinsen, eine Belohnung, einen Rabatt oder ein Erbe geändert wurde; und über den KI-Connector blieb der Wert eines Erbes erhalten, wenn die Einzahlung auf Einkommen geändert wurde, oder der eines Einkommens bei einer Änderung auf Inherited, obwohl beide an verschiedenen Tagen bestimmt werden. Das konnte ein falsches Einkommen oder eine falsche Basis im Steuerjahr der Einzahlung ergeben. Eine solche Änderung bewertet die Einzahlung jetzt neu aus dem Preis (ein Erbe zu seinem Todesdatum), außer es wird ein anderer Wert mitgegeben.
  - **Was zu tun ist:** Hast du eine Einzahlung so geändert, öffne sie und leere Cost Basis, damit sie neu aus dem Preis bewertet wird.

**Weitere Korrekturen** (keine Zahl ändert sich)

- Der Rat von Ledger Review zu einem leeren oder $0-Wert sagt, den Wert einzugeben, wenn BitcoinTX niemanden nach Preisen fragt oder nur dein eigener Mempool, noch nicht installiert oder ohne seine Absicherung, ihn bepreisen könnte, statt ihn leeren zu lassen.
- Eine als "CSV (Macintosh)" eines alten Macs gespeicherte CSV-Datei lässt sich jetzt importieren.
- Die Anleitung sagt, wie das Anmelde-Cookie von BitcoinTX bei BitcoinTX bleibt, wenn andere Dienste unter derselben Adresse geöffnet werden, und Set Login Credentials sagt, was ein neues Passwort gültig lässt: Jeder Browser wird abgemeldet, und ein KI-Schlüssel funktioniert weiter.
- **Sicherheit:** BitcoinTX enthält die neuesten Sicherheitskorrekturen der Software, auf der es aufbaut.

**Bekannte Probleme**

- Nur in einem Journal mit einer Zeile, deren Wert in der Datenbank leer ist (von Hand geleert oder von einer alten Version hinterlassen, in einem seither nicht neu berechneten Journal), kann ein Speichern einen zweiten Versuch brauchen, und ein Wert mit einem Datum nach der letzten Stunde der Preishistorie kann den Tagespreis nehmen, markiert, statt des Stundenpreises. Ledger Review listet einen solchen Wert auf, und dort kannst du den Stundenpreis anwenden.
- BitcoinTX kann ein Form 1099-DA, das die Netzwerkgebühr eines Transfers oder eines Geschenks oder eine Gebühr ohne ihre Auszahlung aufführt, auf Formular 8949 noch nicht abgleichen: Der Complete Tax Report sagt, wie man es von Hand korrigiert.
- Der eigene CSV-Import von BitcoinTX liest einige von Hand erstellte Dateien ohne Meldung: Eine doppelt benannte Spalte nimmt ihren letzten Wert, eine Uhrzeit, die eine Zeitumstellung überspringt oder wiederholt, wird ohne Hinweis als ein Zeitpunkt gelesen, und ein Datum wie 05/03/2024 wird mit dem Monat zuerst gelesen. Vergleiche die Zeilen der Vorschau mit deiner Datei; der eigene Export von BitcoinTX schreibt nichts davon.

[Alles in 2.0.3](${CHANGELOG})`,
    pl_PL: `BitcoinTX 2.0.3 to aktualizacja serwisowa. Poprawia osiem błędów, które mogły zafałszować wynik podatkowy (poniżej, przy każdym to, kogo może dotyczyć i co zrobić), pokazuje monety, których użyje sprzedaż, zanim ją zapiszesz, i poprawia kilka mniejszych błędów. Jej formularze IRS na 2026 r. to wciąż projekty IRS.

**Przed aktualizacją**

- **Przechodzisz z wersji starszej niż 2.0.2?** Najpierw przeczytaj informacje o wersjach pośrednich: poprawki stref czasowych z [2.0.2](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.2/docs/CHANGELOG.md) i [2.0.1](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.1/docs/CHANGELOG.md) mogą poprosić Cię o poprawienie niektórych godzin. Z 1.x także [informacje o 2.0.0](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0): wersja 2.0 zmienia sposób zapisu Twojej księgi, a StartOS nie cofnie tego sam, więc zrób kopię zapasową BitcoinTX w StartOS i zachowaj ją, bo to Twoja droga powrotu do 1.x.

**Po aktualizacji**

- **Odśwież każdą stronę BitcoinTX pozostawioną otwartą** w przeglądarce.
- **Jeśli używasz łącznika AI**, zaktualizuj go: w konfiguracji aplikacji AI zmień wersję po btctx-mcp== na 2.0.3, tak jak podaje ją Settings > Connect an AI Assistant, i uruchom aplikację AI ponownie.
- Potem przeczytaj poprawki poniżej: większość ksiąg nie potrzebuje niczego więcej.

**Formularze IRS na 2026 r.**

- IRS nie opublikował jeszcze ostatecznego formularza 8949 ani Schedule D na 2026 r. Do 31 grudnia Reports oferuje formularze na 2026 r. jako podgląd: projekty IRS, oznaczone DRAFT — DO NOT FILE. Nie składaj ich. Późniejsza aktualizacja przyniesie ostateczne formularze; od 1 stycznia Reports prosi o tę aktualizację. Complete Tax Report i Transaction History działają dla każdego roku.

**Nowości**

- **Formularz Sell pokazuje monety, których używa sprzedaż**, od najstarszych, zanim ją zapiszesz i gdy otworzysz zapisaną: datę nabycia, ilość i koszt każdej partii oraz przychód, zysk i okres, jakie będzie miała na formularzu 8949. Wypłata z giełdy też pokazuje swoje monety. Nic nie jest liczone inaczej.
- **Zmiana wpłaty wycenionej według ceny** (dochód, odsetki, nagroda, rabat, spadek) na My BTC, Gift lub N/A pyta teraz, ile kosztowały monety, tak jak robi to nowa wpłata z tych źródeł. Wpłata zmieniona tak wcześniej zachowuje swoją wartość: jeśli to Twoje własne monety lub prezent, sprawdź, czy jej podstawa kosztowa to kwota zapłacona.

**Poprawki, które mogą zmienić wynik**

- **Monety nabyte 28 lutego i sprzedane 29 lutego następnego roku** były wykazywane jako długoterminowe, a są krótkoterminowe. Zysk się nie zmienia; sprzedaż przechodzi z części II do części I formularza 8949 oraz na Schedule D. Dotyczy to tylko sprzedaży, wydatku, darowizny lub opłaty sieciowej z 29 lutego 2012, 2016, 2020 lub 2024 r. z monet nabytych 28 lutego roku poprzedniego.
  - **Co zrobić:** jeśli masz takie zbycie, uruchom Recalculate Ledger (Settings > Account) i wydrukuj ponownie formularze z tego roku. Jeśli rozliczyłeś już ten rok z nim jako długoterminowym, zapytaj swojego doradcę podatkowego, czy złożyć korektę.
- **Wiersze o tej samej godzinie, wprowadzone przez łącznik AI,** były porządkowane według typu (wpłaty, zakupy, transfery, sprzedaże, wypłaty) zamiast w podanej kolejności, więc sprzedaż i przeniesienie o tej samej godzinie mogły wziąć inne monety niż te same wiersze zaimportowane z pliku: inną podstawę kosztową, inny zysk i inny okres posiadania, w każdym roku podatkowym. Jest to prawdopodobne, gdy AI wprowadza wiersze tylko z datą, którym nadaje godzinę południa.
  - **Co zrobić:** zaktualizuj łącznik AI (powyżej). Jeśli AI wprowadziła w jednym żądaniu wiersze różnych typów na tym samym koncie o tej samej godzinie (lub tego samego dnia bez godziny), porównaj ze swoimi zapisami podstawę kosztową i okres sprzedaży, wydatków i przeniesień z tych kont od tego dnia. Tam, gdzie któraś wzięła inne monety, niż powinna, ustaw wiersze w ich prawdziwej kolejności, zmieniając godzinę (wystarczy minuta różnicy).
- **Godzina wpisana w formularzu transakcji, na urządzeniu ze starymi danymi stref czasowych,** mogła zostać zapisana z przesunięciem o godzinę:
  - Kolumbia Brytyjska, Alberta, Manitoba, Terytoria Północno-Zachodnie i Kuba, od 1 listopada 2026 r.: o godzinę za późno;
  - Maroko, od 20 września 2026 r.: o godzinę za wcześnie;
  - Mołdawia: tylko moment od 03:00 do 04:00 w ostatnią niedzielę marca (o godzinę za wcześnie) lub października (o godzinę za późno);
  - na urządzeniu z danymi z 2024 r. lub starszymi także Paragwaj, od 23 marca do 5 października 2025 r. i od 22 marca do 4 października 2026 r.: o godzinę za późno; z danymi z 2023 r. lub starszymi także Kazachstan (czas Ałmaty i Kostanaju), od 1 marca 2024 r.: o godzinę za wcześnie.

  To zmieniało cenę godziny, którą uzupełnia BitcoinTX, a w pobliżu północy datę: datę na formularzu 8949, okres posiadania i, 31 grudnia, rok podatkowy. BitcoinTX wylicza teraz moment według własnych zasad stref czasowych; na nieaktualnym urządzeniu formularz mówi, że godzina będzie wyświetlana z przesunięciem o godzinę, dopóki urządzenie nie zostanie zaktualizowane.
  - **Co zrobić:** jeśli wpisywałeś transakcje na urządzeniu, które mogło być nieaktualne, w jednym z tych miejsc i okresów, najpierw zaktualizuj urządzenie. Potem otwórz każdą taką transakcję i porównaj jej godzinę z potwierdzeniem, z którego została przepisana; jeśli różni się o godzinę, wpisz ponownie godzinę z potwierdzenia.
- **Kwota bitcoina zapisana w pliku z przecinkiem** ("1,234" albo "2,500" z arkusza kalkulacyjnego, który zapisuje ułamki dziesiętne przecinkiem) była odczytywana jako tysiąc razy większa przez własny import CSV BitcoinTX i import z River, w każdym roku podatkowym. Taka kwota jest teraz odrzucana, z informacją, by zapisywać ułamki dziesiętne kropką; kwoty w dolarach zachowują separator tysięcy.
  - **Co zrobić:** jeśli importowałeś plik z arkusza kalkulacyjnego, poszukaj kwoty bitcoina tysiąc razy za dużej: salda w Dashboard pokazałyby ją od razu.
- **Plik z zabłąkanym cudzysłowem (") tracił wiersze bez słowa,** we własnym imporcie CSV BitcoinTX, w imporcie z River i z każdej innej giełdy: wiersze po nigdy niezamkniętym cudzysłowie albo między dwoma zabłąkanymi znikały, a wiersz z cudzysłowem mógł przejąć tekst późniejszego wiersza. Taki plik jest teraz odrzucany, z informacją, co znaleziono, podobnie jak plik z komórką w więcej niż jednej linii, ze wskazaniem jej wiersza i kolumny. Zabłąkany cudzysłów ma tylko plik edytowany ręcznie lub uszkodzony.
  - **Co zrobić:** jeśli importowałeś plik edytowany ręcznie, porównaj liczbę transakcji zapisanych przez import z liczbą wierszy pliku, dodaj każdą brakującą i sprawdź transakcję tuż przed nimi (jej notatkę, datę nabycia, a w pliku z River jej typ).
- **Wpisana wartość wpłaty pozostawała po zmianie jej źródła.** Koszt wpisany dla My BTC, Gift lub N/A pozostawał jako wartość po zmianie wpłaty na dochód, odsetki, nagrodę, rabat lub spadek; a przez łącznik AI wartość spadku pozostawała po zmianie wpłaty na dochód, lub wartość dochodu po zmianie na Inherited, choć obie ustala się w różnych dniach. Mogło to dać błędny dochód lub podstawę w roku podatkowym wpłaty. Taka zmiana wycenia teraz wpłatę ponownie według ceny (spadek na dzień śmierci), chyba że poda się z nią inną wartość.
  - **Co zrobić:** jeśli zmieniłeś tak wpłatę, otwórz ją i wyczyść Cost Basis, aby została ponownie wyceniona według ceny.

**Inne poprawki** (żaden wynik się nie zmienia)

- Rada Ledger Review dla wartości pustej lub $0 mówi, by wpisać wartość, gdy BitcoinTX nikogo nie pyta o ceny albo gdy wycenić ją mógłby tylko Twój własny Mempool, jeszcze niezainstalowany lub bez swojej kopii zapasowej, zamiast mówić, by ją wyczyścić.
- Plik CSV zapisany jako "CSV (Macintosh)" starego Maca teraz się importuje.
- Instrukcje mówią, jak zachować ciasteczko logowania BitcoinTX tylko dla BitcoinTX, gdy inne usługi są otwierane pod tym samym adresem, a Set Login Credentials mówi, co nowe hasło pozostawia ważne: każda przeglądarka zostaje wylogowana, a klucz AI działa dalej.
- **Bezpieczeństwo:** BitcoinTX zawiera najnowsze poprawki bezpieczeństwa oprogramowania, na którym jest zbudowany.

**Znane problemy**

- Tylko w księdze z wierszem, którego wartość jest pusta w bazie danych (wyczyszczona ręcznie albo pozostawiona przez starą wersję w księdze nieprzeliczanej od tamtej pory), zapis może wymagać drugiej próby, a wartość z datą późniejszą niż ostatnia godzina historii cen może wziąć cenę dnia, oznaczoną, zamiast ceny godziny. Ledger Review wymienia taką wartość i można tam zastosować cenę godziny.
- BitcoinTX nie potrafi jeszcze dopasować na formularzu 8949 Form 1099-DA, który podaje opłatę sieciową transferu lub prezentu albo opłatę bez jej wypłaty: Complete Tax Report mówi, jak poprawić to ręcznie.
- Własny import CSV BitcoinTX odczytuje bez słowa niektóre pliki tworzone ręcznie: kolumna nazwana dwa razy bierze ostatnią wartość, godzina, którą zmiana czasu pomija lub powtarza, jest odczytywana jako jeden moment bez żadnej uwagi, a data taka jak 05/03/2024 jest odczytywana z miesiącem na początku. Porównaj wiersze podglądu ze swoim plikiem; własny eksport BitcoinTX nie zapisuje żadnej z tych rzeczy.

[Wszystko w 2.0.3](${CHANGELOG})`,
    fr_FR: `BitcoinTX 2.0.3 est une mise à jour de maintenance. Elle corrige huit bugs qui pouvaient fausser un chiffre fiscal (ci-dessous, chacun avec qui peut être concerné et que faire), montre les bitcoins qu’une vente utilise avant de l’enregistrer, et corrige quelques bugs mineurs. Ses formulaires de l’IRS pour 2026 sont encore les brouillons de l’IRS.

**Avant la mise à jour**

- **Vous venez d’une version antérieure à la 2.0.2 ?** Lisez d’abord les notes des versions intermédiaires : les corrections des fuseaux horaires de [la 2.0.2](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.2/docs/CHANGELOG.md) et de [la 2.0.1](https://github.com/DigiMonk73/BTCTX-MCP/blob/v2.0.1/docs/CHANGELOG.md) peuvent vous demander de corriger certaines heures. Depuis la 1.x, aussi [celles de la 2.0.0](https://github.com/DigiMonk73/BTCTX-MCP/releases/tag/v2.0.0) : la 2.0 change la façon dont votre registre est enregistré, et StartOS ne peut pas l’annuler tout seul, alors faites une sauvegarde StartOS de BitcoinTX et gardez-la, car c’est votre chemin de retour vers la 1.x.

**Après la mise à jour**

- **Rechargez toute page de BitcoinTX restée ouverte** dans un navigateur.
- **Si vous utilisez un connecteur IA**, mettez-le à jour : dans la configuration de votre application d’IA, remplacez la version qui suit btctx-mcp== par 2.0.3, comme l’indique Settings > Connect an AI Assistant, puis redémarrez l’application d’IA.
- Puis lisez les corrections ci-dessous : la plupart des registres n’ont besoin de rien d’autre.

**Les formulaires de l’IRS pour 2026**

- L’IRS n’a pas encore publié le formulaire 8949 ni le Schedule D définitifs de 2026. Jusqu’au 31 décembre, Reports propose ceux de 2026 en aperçu : les brouillons de l’IRS, marqués DRAFT — DO NOT FILE. Ne les déposez pas. Une mise à jour ultérieure apporte les formulaires définitifs ; à partir du 1er janvier, Reports demande cette mise à jour. Le Complete Tax Report et le Transaction History fonctionnent pour toute année.

**Nouveautés**

- **Le formulaire Sell montre les bitcoins qu’une vente utilise**, les plus anciens d’abord, avant de l’enregistrer et à l’ouverture d’une vente enregistrée : la date d’acquisition, la quantité et le coût de chaque lot, ainsi que le produit, le gain et la durée qu’elle aura sur le formulaire 8949. Un retrait d’une plateforme d’échange montre aussi ses bitcoins. Rien n’est calculé autrement.
- **Changer un dépôt valorisé d’après le prix** (revenu, intérêts, récompense, remise, héritage) en My BTC, Gift ou N/A demande maintenant ce que les bitcoins ont coûté, comme le fait un nouveau dépôt de ces origines. Un dépôt changé ainsi auparavant garde sa valeur : s’il s’agit de vos propres bitcoins ou d’un don, vérifiez que sa base de coût est ce qui a été payé.

**Corrections qui peuvent changer un chiffre**

- **Des bitcoins acquis le 28 février et vendus le 29 février de l’année suivante** étaient déclarés à long terme, mais ils sont à court terme. Le gain reste le même ; la vente passe de la partie II à la partie I du formulaire 8949, et sur le Schedule D. Cela ne touche qu’une vente, une dépense, un don ou des frais de réseau du 29 février 2012, 2016, 2020 ou 2024 portant sur des bitcoins acquis le 28 février de l’année précédente.
  - **Que faire :** si vous avez une telle cession, lancez Recalculate Ledger (Settings > Account) et imprimez de nouveau les formulaires de cette année. Si vous avez déjà déposé cette année avec elle à long terme, demandez à votre conseiller fiscal s’il faut une déclaration rectificative.
- **Les lignes qui partagent une heure, saisies par le connecteur IA,** étaient rangées par type (dépôts, achats, transferts, ventes, retraits) au lieu de l’ordre donné : une vente et un transfert à la même heure pouvaient donc prendre d’autres bitcoins que les mêmes lignes importées d’un fichier, avec une autre base de coût, un autre gain et une autre durée de détention, pour toute année fiscale. C’est probable quand l’IA saisit des lignes avec une date seule, qu’elle met à midi.
  - **Que faire :** mettez à jour le connecteur IA (ci-dessus). Si une IA a saisi, en une seule demande, des lignes de types différents sur le même compte à la même heure (ou le même jour sans heure), comparez avec vos relevés la base de coût et la durée des ventes, dépenses et transferts sortants de ces comptes à partir de ce jour. Là où l’une a pris d’autres bitcoins qu’elle n’aurait dû, remettez les lignes dans leur ordre réel en modifiant une heure (une minute d’écart suffit).
- **Une heure saisie dans le formulaire de transaction, sur un appareil aux données de fuseaux horaires anciennes,** pouvait être enregistrée avec une heure d’écart :
  - la Colombie-Britannique, l’Alberta, le Manitoba, les Territoires du Nord-Ouest et Cuba, à partir du 1er novembre 2026 : une heure trop tard ;
  - le Maroc, à partir du 20 septembre 2026 : une heure trop tôt ;
  - la Moldavie : seulement un moment entre 03:00 et 04:00 le dernier dimanche de mars (une heure trop tôt) ou d’octobre (une heure trop tard) ;
  - sur un appareil dont les données datent de 2024 ou avant, aussi le Paraguay, du 23 mars au 5 octobre 2025 et du 22 mars au 4 octobre 2026 : une heure trop tard ; si elles datent de 2023 ou avant, aussi le Kazakhstan (l’heure d’Almaty et de Kostanaï), à partir du 1er mars 2024 : une heure trop tôt.

  Cela changeait le prix de l’heure que BitcoinTX remplit et, près de minuit, la date : la date sur le formulaire 8949, la durée de détention et, le 31 décembre, l’année fiscale. BitcoinTX calcule maintenant le moment avec ses propres règles horaires ; sur un appareil pas à jour, le formulaire indique que l’heure s’affichera avec une heure d’écart jusqu’à la mise à jour de l’appareil.
  - **Que faire :** si vous avez saisi des transactions sur un appareil qui pouvait ne pas être à jour, dans l’un de ces lieux et périodes, mettez d’abord l’appareil à jour. Ouvrez ensuite chacune de ces transactions et comparez son heure avec le reçu dont vous l’avez recopiée ; s’il y a une heure d’écart, saisissez de nouveau l’heure du reçu.
- **Un montant en bitcoin écrit avec une virgule dans un fichier** ("1,234", ou "2,500" venant d’un tableur qui écrit les décimales avec une virgule) était lu mille fois plus grand par l’import CSV propre à BitcoinTX et par celui de River, pour toute année fiscale. Un tel montant est maintenant refusé, avec l’indication d’écrire les décimales avec un point ; les dollars gardent leur séparateur de milliers.
  - **Que faire :** si vous avez importé un fichier venant d’un tableur, cherchez un montant en bitcoin mille fois trop grand : les avoirs du Dashboard le montreraient tout de suite.
- **Un fichier avec un guillemet (") égaré perdait des lignes sans rien dire,** dans l’import CSV propre à BitcoinTX, dans celui de River et dans celui de toute autre plateforme d’échange : les lignes après un guillemet jamais fermé, ou entre deux guillemets égarés, disparaissaient, et la ligne portant le guillemet pouvait prendre le texte d’une ligne suivante. Un tel fichier est maintenant refusé, en disant ce qui a été trouvé, ainsi qu’un fichier dont une cellule s’étend sur plus d’une ligne, en nommant sa ligne et sa colonne. Seul un fichier modifié à la main ou abîmé a un guillemet égaré.
  - **Que faire :** si vous avez importé un fichier modifié à la main, comparez le nombre de transactions enregistrées par l’import avec les lignes du fichier, ajoutez celle qui manque et vérifiez la transaction juste avant (sa note, sa date d’acquisition et, pour le fichier de River, son type).
- **La valeur saisie d’un dépôt était gardée quand son origine changeait.** Un coût saisi pour My BTC, Gift ou N/A était gardé comme valeur quand le dépôt passait en revenu, intérêts, récompense, remise ou héritage ; et, par le connecteur IA, la valeur d’un héritage était gardée quand le dépôt passait en revenu, ou celle d’un revenu quand il passait en Inherited, alors que les deux se prennent à des dates différentes. Cela pouvait mettre un revenu ou une base faux dans l’année fiscale du dépôt. Un tel changement valorise maintenant le dépôt de nouveau d’après le prix (un héritage à sa date de décès), sauf si une autre valeur est donnée avec lui.
  - **Que faire :** si vous avez changé un dépôt ainsi, ouvrez-le et videz Cost Basis pour qu’il soit de nouveau valorisé d’après le prix.

**Autres corrections** (aucun chiffre ne change)

- Le conseil de Ledger Review pour une valeur vide ou à 0 $ dit de saisir la valeur quand BitcoinTX ne demande les prix à personne, ou quand seul votre propre Mempool, pas encore installé ou sans sa solution de secours, pourrait la valoriser, au lieu de dire de la vider.
- Un fichier CSV enregistré au format "CSV (Macintosh)" d’un ancien Mac s’importe maintenant.
- Les instructions expliquent comment garder le cookie de connexion de BitcoinTX pour BitcoinTX seul quand d’autres services sont ouverts à la même adresse, et Set Login Credentials dit ce qu’un nouveau mot de passe laisse valable : chaque navigateur est déconnecté, et une clé IA continue de fonctionner.
- **Sécurité :** BitcoinTX inclut les derniers correctifs de sécurité des logiciels sur lesquels il repose.

**Problèmes connus**

- Uniquement dans un registre avec une ligne dont la valeur est vide dans la base de données (vidée à la main, ou laissée par une ancienne version dans un registre non recalculé depuis), un enregistrement peut demander un second essai, et une valeur datée après la dernière heure de l’historique des prix peut prendre le prix du jour, marqué, au lieu de celui de l’heure. Ledger Review liste une telle valeur, et vous pouvez y appliquer le prix de l’heure.
- BitcoinTX ne peut pas encore rapprocher sur le formulaire 8949 un Form 1099-DA qui indique les frais de réseau d’un transfert ou d’un don, ou des frais sans leur retrait : le Complete Tax Report dit comment le corriger à la main.
- L’import CSV propre à BitcoinTX lit sans rien dire certains fichiers faits à la main : une colonne nommée deux fois prend sa dernière valeur, une heure qu’un changement d’heure saute ou répète est lue comme un seul moment sans aucune note, et une date comme 05/03/2024 est lue mois en premier. Comparez les lignes de l’aperçu avec votre fichier ; l’export propre à BitcoinTX n’écrit rien de tout cela.

[Tout ce que contient la 2.0.3](${CHANGELOG})`,
  },
  migrations: {
    up: async ({ effects }) => {},
    down: IMPOSSIBLE,
  },
})

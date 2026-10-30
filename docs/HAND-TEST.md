# Testing BitcoinTX by hand

**A throwaway install only, never your records.** This guide imports made-up
ledgers and deletes transactions. Nothing in these files comes from anyone's
real account.

You'll need about 15 minutes for Parts 1 and 2, and another 20 for Part 3. Do
them in order: Part 3 adds accounts that would change what Part 2 shows.

## Before you start

### Where to try it

Use one of these, and nothing else:

- **BitcoinTX Preview on your Mac**, only if it holds nothing you want to keep.
- **A throwaway Docker install**, which you remove at the end. In a Terminal
  window, with `VERSION` being the version you're testing (for example
  `v2.0.0-beta.2`):

  ```bash
  docker run -d --name btctx-handtest -p 127.0.0.1:8090:80 -v btctx-handtest:/data ghcr.io/digimonk73/btctx-mcp:VERSION
  ```

  Open <http://localhost:8090>. To create the login you'll need the setup
  code, which this prints:

  ```bash
  docker logs btctx-handtest
  ```

Never use the BitcoinTX app that holds your real ledger, or your StartOS
server's copy.

### Getting a file

Open this guide on GitHub, on the branch you're testing. Click a file's name,
then the **Download raw file** button (a down arrow, top right of the file).

### Start empty, with the tax timezone on UTC

1. In **Settings**, open **Data Management**. If there are transactions, press
   **Delete** beside **Delete All Transactions**, type `DELETE`, and confirm.
2. In **Settings**, open **Account**. Under **Tax Timezone**, choose `UTC` and
   press **Save**.

The figures below are for UTC. A new install starts on your computer's
timezone, and a sale near midnight or a year's end could then fall on another
day. So check this first.

## Part 1: the template

This is the sample file BitcoinTX offers to anyone starting with a CSV.

1. In **Settings**, open **Data Management**. Under **Import Transactions
   (CSV)**, press **Template** and save the file.
2. Choose that file with the file button beside **Preview**, then press
   **Preview**.
3. Check the preview, press its Import button, and press **OK** when your
   browser asks you to confirm. Then read the lines under **Portfolio Overview**
   on the **Dashboard**.

<!-- begin template -->
- **The preview:** "22 valid / 22 total rows", with no errors and no warnings.
- **The button:** "Import 22 Transactions".
- **Afterwards:** Bank (USD) $7,990.00, Exchange (USD) $12,940.00, Exchange (BTC) 0.59990000 BTC, Wallet (BTC) 0.58055000 BTC.
<!-- end template -->

4. Delete the transactions again: **Data Management**, **Delete**, type `DELETE`.

## Part 2: each exchange's file

Some rows here have no dollar value in the file, so BitcoinTX needs a price.

1. In **Settings**, open **Privacy & Network**, choose **Public price sites**
   and save. Your throwaway install can now ask those sites for prices.

Then, for each file below:

2. In **Settings**, open **Import from an exchange**. Choose the **Exchange
   file** it says, then the file, then press **Preview**.
3. Check the rows and the warnings against the list below. A warning says why
   a row is left out or needs a look: each one here is meant to be there.
4. Press the button that says **Import … Transaction(s)**, and **OK** when your
   browser asks you to confirm. If BitcoinTX then asks about earlier tax years,
   press **Save anyway (a copy is made first)**.
5. Check **Portfolio Overview** on the **Dashboard**, as in Part 1. A line the
   list doesn't name should read zero. A bank below zero is right: these files
   don't list the dollars that first came in.
6. Delete the transactions before the next file (**Data Management**,
   **Delete**, type `DELETE`), unless the next file says not to.

**Dollar values marked "est."** in a preview are real prices from those sites,
so they aren't listed here. Everything else should match exactly.

<!-- begin files -->
#### [river_bitcoin_activity.csv](../testdata/exchange_files/river_bitcoin_activity.csv) (Bitcoin activity: each kind of row River's file has)

- **Exchange file:** River.
- **The preview:** 14 rows in the file, button "Import 13 Transaction(s)", no errors, 2 warnings:
  - Row 14: From your wallet, oldest coins first: you can choose the coins after the import.
  - Row 15: Unrecognized row pattern (tag=none, sent=USD, received=-) — skipped.
- **Afterwards:** Bank (USD) −$300.00, Exchange (USD) $54.50, Exchange (BTC) 0.00125300 BTC, Wallet (BTC) 0.00130000 BTC.

#### [coinbase_2021.csv](../testdata/exchange_files/coinbase_2021.csv) (the oldest statement)

- **Exchange file:** Coinbase.
- **The preview:** 2 rows in the file, button "Import 2 Transaction(s)", no errors, 0 warnings.
- **Afterwards:** Bank (USD) −$111.99, Exchange (USD) $35.47, Exchange (BTC) 0.00100000 BTC.

#### [coinbase_2022.csv](../testdata/exchange_files/coinbase_2022.csv) (a statement from before 2024)

- **Exchange file:** Coinbase.
- **The preview:** 2 rows in the file, button "Import 2 Transaction(s)", no errors, 0 warnings.
- **Afterwards:** Bank (USD) −$87.99, Exchange (USD) $44.33, Exchange (BTC) 0.00100000 BTC.

#### [coinbase_2024.csv](../testdata/exchange_files/coinbase_2024.csv) (a statement with an ID column first)

- **Exchange file:** Coinbase.
- **The preview:** 11 rows in the file, button "Import 6 Transaction(s)", no errors, 5 warnings:
  - Rows 10 and 11 trade bitcoin for another asset (“Convert”): add each by hand, bitcoin given up as a Withdrawal, purpose Spent, with its dollar value as proceeds (a disposal: IRS Notice 2014-21), bitcoin received as a Deposit with its dollar value as cost basis: left out.
  - Row 12 is ETH, not bitcoin (BitcoinTX tracks bitcoin only): left out.
  - Row 13 moves dollars, not bitcoin (“Deposit”): left out.
  - Row 14 is “Pro Withdrawal”, which this mapping leaves out: left out.
  - Row 7: From your wallet, oldest coins first: you can choose the coins after the import.
- **Afterwards:** Bank (USD) −$99.99, Exchange (USD) $49.70, Exchange (BTC) 0.00041300 BTC, Wallet (BTC) 0.00010000 BTC.

#### [coinbase_2026.csv](../testdata/exchange_files/coinbase_2026.csv) (today's statement, of 13 columns)

- **Exchange file:** Coinbase.
- **The preview:** 6 rows in the file, button "Import 6 Transaction(s)", no errors, 0 warnings.
- **Afterwards:** Bank (USD) −$44.90, Exchange (USD) $24.41, Exchange (BTC) 0.00022870 BTC.

#### [coinbase_advance_trade.csv](../testdata/exchange_files/coinbase_advance_trade.csv) (Advanced Trade's rows)

- **Exchange file:** Coinbase.
- **The preview:** 3 rows in the file, button "Import 3 Transaction(s)", no errors, 0 warnings.
- **Afterwards:** Bank (USD) −$80.48, Exchange (USD) $40.75, Exchange (BTC) 0.00051000 BTC.

#### [kraken_ledgers.csv](../testdata/exchange_files/kraken_ledgers.csv) (a ledger of each kind of row)

- **Exchange file:** Kraken.
- **The preview:** 20 rows in the file, button "Import 6 Transaction(s)", no errors, 8 warnings:
  - Row 9 is Kraken's pending copy of a deposit or withdrawal (no txid), whose completed row is read: left out.
  - Rows 2 and 21 move dollars, not bitcoin: left out.
  - Rows 12 and 13 move coins between Kraken's own balances (spot, staking, earn): left out.
  - Rows 15 and 16 are ETH, not bitcoin (BitcoinTX tracks bitcoin only): left out.
  - Rows 17 and 18 trade bitcoin for ETH: add each by hand (bitcoin given up as a Withdrawal, purpose Spent, at its dollar value: a disposal, IRS Notice 2014-21): left out.
  - Rows 19 and 20 are a withdrawal Kraken sent back (they add up to nothing): left out.
  - Row 11: From your wallet, oldest coins first: you can choose the coins after the import.
  - Row 14: 0.0000012345 BTC is rounded to 0.00000123 BTC: BitcoinTX counts whole satoshis.
- **Afterwards:** Bank (USD) −$501.30, Exchange (USD) $107.96, Exchange (BTC) 0.00296623 BTC, Wallet (BTC) 0.00100000 BTC.

#### [kraken_fee_credits.csv](../testdata/exchange_files/kraken_fee_credits.csv) (trades paid with fee credits)

- **Exchange file:** Kraken.
- **The preview:** 7 rows in the file, button "Import 2 Transaction(s)", no errors, 2 warnings:
  - Row 2 is KFEE, not bitcoin (BitcoinTX tracks bitcoin only): left out.
  - Rows 5 and 6 paid a fee with Kraken fee credits (KFEE), which aren't your money: the credits count as no fee.
- **Afterwards:** Bank (USD) −$200.00, Exchange (USD) $104.88, Exchange (BTC) 0.00100000 BTC.

#### [strike_activity.csv](../testdata/exchange_files/strike_activity.csv) (the Activity report)

- **Exchange file:** Strike.
- **The preview:** 3 rows in the file, button "Import 1 Transaction(s)", no errors, 2 warnings:
  - Row 3 is Pending, not completed: left out.
  - Row 4 is Reversed, not completed: left out.
- **Afterwards:** Bank (USD) −$25.25, Exchange (BTC) 0.00025000 BTC.

#### [strike_statement.csv](../testdata/exchange_files/strike_statement.csv) (a statement)

- **Exchange file:** Strike.
- **The preview:** 11 rows in the file, button "Import 5 Transaction(s)", no errors, 5 warnings:
  - Rows 9 and 10 were reversed or cancelled (their pieces add up to nothing): left out.
  - Row 2 moves dollars, not bitcoin (“Deposit”): left out.
  - Row 11 moves dollars, not bitcoin (“Withdrawal”): left out.
  - Row 12 is “Bitcoin Back”, a kind of row this mapping doesn't read (add it by hand if it moved bitcoin): left out.
  - Row 6: From your wallet, oldest coins first: you can choose the coins after the import.
- **Afterwards:** Bank (USD) −$301.00, Exchange (USD) $49.50, Exchange (BTC) 0.00237500 BTC, Wallet (BTC) 0.00010000 BTC.

#### [swan_deposits_and_purchases.csv](../testdata/exchange_files/swan_deposits_and_purchases.csv) (deposits and purchases)

- **Exchange file:** Swan: deposits and purchases.
- **The preview:** 7 rows in the file, button "Import 3 Transaction(s)", no errors, 5 warnings:
  - Row 4 moves dollars, not bitcoin (“deposit”): left out.
  - Row 7 is pending, not completed: left out.
  - Row 8 is Swan moving coins between its custodians: they never left Swan: left out.
  - Row 10 moves dollars, not bitcoin (“monthly_fee”): left out.
  - Row 9: From your wallet, oldest coins first: you can choose the coins after the import.
- **Untick row 9** (its Import box). The button then says "Import 2 Transaction(s)". Its coins come from a wallet that holds none here: left ticked, the import stops at "Not enough BTC" and saves nothing, as it should.
- **Afterwards:** Bank (USD) −$150.00, Exchange (BTC) 0.00165000 BTC.

#### [swan_withdrawals.csv](../testdata/exchange_files/swan_withdrawals.csv) (withdrawals)

- **First:** import swan_deposits_and_purchases.csv as above, and don't delete it: this file sends its coins.
- **Exchange file:** Swan: withdrawals.
- **The preview:** 3 rows in the file, button "Import 1 Transaction(s)", no errors, 2 warnings:
  - Row 5 was canceled: left out.
  - Row 6 hasn't been sent (no Executed At): left out.
- **Afterwards:** Bank (USD) −$150.00, Exchange (BTC) 0.00015000 BTC, Wallet (BTC) 0.00150000 BTC.

#### [cash_app_bitcoin.csv](../testdata/exchange_files/cash_app_bitcoin.csv) (the Bitcoin file)

- **Exchange file:** Cash App.
- **The preview:** 7 rows in the file, button "Import 6 Transaction(s)", no errors, 3 warnings:
  - Row 8 is “Bitcoin Payment”, a kind of row this mapping doesn't read (add it by hand if it moved bitcoin): left out.
  - Row 5: This send's fee is $2.00: BitcoinTX records a send's fee in BTC, so it isn't read. Add it in BTC if it belongs in the figures.
  - Row 7: From your wallet, oldest coins first: you can choose the coins after the import.
- **Afterwards:** Bank (USD) −$110.15, Exchange (USD) $48.51, Exchange (BTC) 0.00050500 BTC, Wallet (BTC) 0.00010000 BTC.

#### [cash_app_activity.csv](../testdata/exchange_files/cash_app_activity.csv) (the activity file)

- **Exchange file:** Cash App.
- **The preview:** 3 rows in the file, button "Import 1 Transaction(s)", no errors, 2 warnings:
  - Row 3 is FAILED, not completed: left out.
  - Row 4 isn't bitcoin (its asset is blank): left out.
- **Afterwards:** Bank (USD) −$1,010.00, Exchange (BTC) 0.01000000 BTC.
<!-- end files -->

## Part 3: the reference ledger

This is the [reference ledger](../testdata/reference_ledger.csv), the same test
ledger BitcoinTX's own automatic checks use: 16 accounts and every kind of
transaction, from 2022 to 2026, with every Form 8949 box of 2024 to 2026. An
automatic test already imports this file and compares every figure. Here you
see that the screens get there too.

### Add the accounts first

The file names each account, and an import refuses a name it doesn't know.

1. Make sure the ledger has no transactions.
2. In **Settings**, open **Wallets, exchanges and banks**. A new install
   already has Bank, Wallet and Exchange (its two accounts, Exchange USD and
   Exchange BTC, are in the file). Add these, in this order, each with its
   button, typing the name exactly:

<!-- begin accounts -->
| Button | Name to type | Does this exchange send you a Form 1099-DA? |
| --- | ---: | ---: |
| Add a wallet | Coldcard | not asked |
| Add a wallet | Jade | not asked |
| Add an exchange | Kraken | Yes |
| Add an exchange | Overseas | No |
| Add a bank | Credit union | not asked |
| Add a bank | Savings | not asked |
| Add a wallet | Sparrow | not asked |
| Add a wallet | Trezor | not asked |
<!-- end accounts -->

Adding the exchange Kraken makes two accounts, Kraken USD and Kraken BTC, and
Overseas the same.

### Import it

3. Download [reference_ledger.csv](../testdata/reference_ledger.csv).
4. In **Settings**, open **Data Management**. Choose the file with the file
   button beside **Preview**, press **Preview**, and check:

<!-- begin reference-preview -->
- **The preview:** "213 valid / 213 total rows", with no errors and no warnings.
- **The button:** "Import 213 Transactions".
<!-- end reference-preview -->

5. Press the Import button, and **OK** when your browser asks you to confirm.

### Hide one, and try a rename

6. In **Wallets, exchanges and banks**, open **Jade** and press **Hide**. It
   still holds coins, and they stay in every figure: the ledger keeps it this way.
7. If you'd like to try a rename: open **Overseas**, change its name to
   `Offshore`, press **Rename**, and see the new name on the Dashboard. Then
   open it again and rename it back to `Overseas`, because the tables below use
   that name. No figure changes.

### Compare the figures

8. Go to **Reports**. For each tax year below, choose the year, choose
   **Complete Tax Report**, and press **Export**.
9. Compare with the tables below:
   - the boxes, under **Form 8949 and Schedule D** in section 1, "Summary";
   - income, under **Income** in the same section;
   - rebates, under **Rebates (not income)** in section 3, "Income";
   - holdings, in the table at the top of section 5, "Holdings at year end".
10. For 2024, 2025 and 2026, also choose **IRS Reports (Form 8949, Schedule D,
    etc.)** and press **Export**. Each Schedule D line holds the same totals as
    its box below. BitcoinTX has no IRS forms for 2023: its report is the check.

The report's **Market value** isn't listed, since it depends on the price
source you chose.

<!-- begin figures -->
### 2023

| Box | Schedule D line | Rows | Proceeds | Cost basis | Gain (loss) |
| --- | ---: | ---: | ---: | ---: | ---: |
| C | 3 | 7 | $6,125.61 | $4,308.57 | $1,817.04 |

**Income:** Income $5,550.00, Interest $1,350.00, Reward $3,099.12; total $9,999.12.

**Rebates (not income):** 0.00020000 BTC, $7.50.

**Holdings at December 31, 2023:**

| Account | Lots | BTC | Cost basis |
| --- | ---: | ---: | ---: |
| Exchange BTC | 3 | 1.24995000 | $30,038.35 |
| Kraken BTC | 1 | 0.05000000 | $3,400.00 |
| Trezor | 1 | 0.01000000 | $259.12 |
| Wallet | 10 | 1.56508000 | $37,821.68 |
| **Total** | **15** | **2.87503000** | **$71,519.15** |

### 2024

| Box | Schedule D line | Rows | Proceeds | Cost basis | Gain (loss) |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1b | 1 | $2,494.49 | $1,150.92 | $1,343.57 |
| B | 2 | 1 | $499.25 | $230.00 | $269.25 |
| C | 3 | 2 | $3,196.55 | $3,883.65 | ($687.10) |
| D | 8b | 1 | $12,460.51 | $5,249.16 | $7,211.35 |
| E | 9 | 1 | $9,727.50 | $3,457.50 | $6,270.00 |
| F | 10 | 15 | $15,477.07 | $10,310.22 | $5,166.85 |

**Income:** Income $15,505.00, Interest $195.00, Reward $6,500.00; total $22,200.00.

**Rebates (not income):** 0.00015000 BTC, $14.00.

**Holdings at December 31, 2024:**

| Account | Lots | BTC | Cost basis |
| --- | ---: | ---: | ---: |
| Exchange BTC | 6 | 1.70000000 | $109,455.50 |
| Kraken BTC | 1 | 0.05000000 | $3,653.65 |
| Trezor | 2 | 0.01295000 | $511.00 |
| Wallet | 20 | 2.55589500 | $82,017.45 |
| **Total** | **29** | **4.31884500** | **$195,637.60** |

### 2025

| Box | Schedule D line | Rows | Proceeds | Cost basis | Gain (loss) |
| --- | ---: | ---: | ---: | ---: | ---: |
| G | 1b | 2 | $14,732.44 | $7,517.61 | $7,214.83 |
| H | 2 | 4 | $25,227.18 | $15,080.41 | $10,146.77 |
| I | 3 | 8 | $16,263.61 | $10,015.96 | $6,247.65 |
| J | 8b | 1 | $10,480.81 | $4,256.80 | $6,224.01 |
| K | 9 | 10 | $81,781.82 | $34,113.93 | $47,667.89 |
| L | 10 | 16 | $6,181.66 | $4,157.02 | $2,024.64 |

**Income:** Income $10,500.00, Interest $210.00, Reward $3,450.00; total $14,160.00.

**Rebates (not income):** 0.04030000 BTC, $5,624.31.

**Holdings at December 31, 2025:**

| Account | Lots | BTC | Cost basis |
| --- | ---: | ---: | ---: |
| Exchange BTC | 7 | 0.88480000 | $94,167.38 |
| Sparrow | 4 | 0.05585000 | $3,590.10 |
| Trezor | 3 | 0.01225000 | $509.40 |
| Wallet | 30 | 2.68369000 | $111,523.89 |
| **Total** | **44** | **3.63659000** | **$209,790.77** |

### 2026

| Box | Schedule D line | Rows | Proceeds | Cost basis | Gain (loss) |
| --- | ---: | ---: | ---: | ---: | ---: |
| G | 1b | 6 | $29,554.34 | $29,056.21 | $498.13 |
| H | 2 | 3 | $26,929.93 | $19,931.00 | $6,998.93 |
| I | 3 | 23 | $10,283.05 | $10,192.42 | $90.63 |
| J | 8b | 1 | $27,309.37 | $18,516.96 | $8,792.41 |
| K | 9 | 9 | $35,676.42 | $22,680.45 | $12,995.97 |
| L | 10 | 15 | $9,259.82 | $1,635.73 | $7,624.09 |

**Income:** Income $2,349.00, Interest $528.65, Reward $716.00; total $3,593.65.

**Rebates (not income):** 0.00130000 BTC, $184.20.

**Holdings at December 31, 2026:**

| Account | Lots | BTC | Cost basis |
| --- | ---: | ---: | ---: |
| Coldcard | 6 | 1.11695000 | $39,705.96 |
| Exchange BTC | 4 | 0.11494000 | $14,105.70 |
| Jade | 8 | 0.03617000 | $4,745.70 |
| Kraken BTC | 7 | 0.01256000 | $1,756.87 |
| Overseas BTC | 4 | 0.00547000 | $766.35 |
| Sparrow | 4 | 0.04265000 | $2,561.85 |
| Trezor | 6 | 0.01565000 | $763.55 |
| Wallet | 35 | 1.99969000 | $134,634.26 |
| **Total** | **74** | **3.34408000** | **$199,040.24** |
<!-- end figures -->

## If something doesn't match

Stop there, and note the file, the year or row, and the figure you expected and
the one you saw. These files are made up, so you can quote them anywhere. Never
quote figures from a real ledger.

Open an issue at <https://github.com/DigiMonk73/BTCTX-MCP/issues>, or say it in
your chat with Claude.

## When you're done

For the throwaway Docker install, remove it and its data:

```bash
docker rm -f btctx-handtest
```

```bash
docker volume rm btctx-handtest
```

For BitcoinTX Preview: in **Data Management**, delete the transactions. Then in
**Wallets, exchanges and banks**, delete each account you added.

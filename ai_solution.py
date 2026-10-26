```python
def map_coinbase(mapper, row):
    date = row.get("Date", "")
    if not date:
        return None
    type = row.get("Type", "")
    if "Buy" in type or "Sell" in type:
        mapper.maybe_touch('Buy/Sell')
        if "Advance Trade Buy" in type:
            return {'Buy/Sell': 'Buy', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Price': row.get('Price'), 'Fees': row.get('Fees')}
        if "Advanced Trade Buy" in type:
            return {'Buy/Sell': 'Buy', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Price': row.get('Price'), 'Fees': row.get('Fees')}
        if "Advance Trade Sell" in type:
            return {'Buy/Sell': 'Sell', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Price': row.get('Price'), 'Fees': row.get('Fees')}
        if "Advanced Trade Sell" in type:
            return {'Buy/Sell': 'Sell', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Price': row.get('Price'), 'Fees': row.get('Fees')}
    if "Reward Income" in type:
        return {'Income': 'Reward', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Currency': row.get('Currency'), 'Fees': row.get('Fees')}
    if "Reward Income" in type:
        return {'Income': 'Reward', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Currency': row.get('Currency'), 'Fees': row.get('Fees')}
    if type == "Interest Income":
        return {'Income': 'Interest', 'Asset': row.get('Asset'), 'Amount': row.get('Amount'), 'Currency': row.get('Currency'), 'Fees': row.get('Fees')}
    return None
```
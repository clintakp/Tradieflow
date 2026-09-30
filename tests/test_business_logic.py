from app import invoice_totals

def test_gst():
    assert invoice_totals(100)==(100.0,10.0,110.0)
def test_rounding():
    assert invoice_totals(199.99)==(199.99,20.0,219.99)

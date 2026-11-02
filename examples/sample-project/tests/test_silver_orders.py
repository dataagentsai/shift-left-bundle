from shop.silver_orders import clean_orders


def test_clean_orders(spark):
    df = spark.createDataFrame([(1, 10.0), (1, 10.0), (2, -5.0)], "order_id INT, amount DOUBLE")
    assert clean_orders(df).count() == 1


def test_tag_big_orders(spark):
    from shop.silver_orders import tag_big_orders
    df = spark.createDataFrame([(1, 500.0), (2, 50.0)], "order_id INT, amount DOUBLE")
    got = {r.order_id: r.is_big for r in tag_big_orders(df, 100.0).collect()}
    assert got == {1: True, 2: False}

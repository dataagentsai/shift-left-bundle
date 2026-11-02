"""Empty-table plan harness (SL-052). Runs in a Python that has PySpark; imports nothing from shiftleft.

    python -I plan_harness.py request.json result.json

request: {"roots": ["/abs/src", ...], "cases": [{"module": "shop.gold_kpis", "function": "clean_region",
          "inputs": {"orders": "order_id INT, region STRING"}}]}
Each input is an EMPTY DataFrame built from an empty RDD with the given schema. An empty local list or
df.limit(0) would let Spark fold the plan away and hide a cartesian product (found 2 Nov 2026).
"""
import importlib
import json
import os
import sys
import traceback


def main(req_path, out_path):
    req = json.load(open(req_path))
    os.environ.setdefault("TZ", "UTC")
    os.environ["PYSPARK_PYTHON"] = sys.executable
    from pyspark.sql import SparkSession
    spark = (SparkSession.builder.master("local[1]").appName("shiftleft-plans").config("spark.ui.enabled", "false")
             .config("spark.sql.shuffle.partitions", "1").config("spark.sql.adaptive.enabled", "false").getOrCreate())
    spark.sparkContext.setLogLevel("ERROR")
    for r in req["roots"]:
        sys.path.insert(0, r)
    results = []
    for case in req["cases"]:
        res = {"module": case["module"], "function": case["function"]}
        try:
            fn = getattr(importlib.import_module(case["module"]), case["function"])
            args = {k: spark.createDataFrame(spark.sparkContext.emptyRDD(), v) for k, v in case["inputs"].items()}
            df = fn(**args)
            if not hasattr(df, "_jdf"):
                res.update(ok=False, skipped=True, error=f"returns {type(df).__name__}, not a DataFrame")
                results.append(res)
                continue
            plan = df._jdf.queryExecution().executedPlan().toString()
            res.update(ok=True, cartesian="CartesianProduct" in plan, nested_loop="BroadcastNestedLoopJoin" in plan,
                       python_udf=("BatchEvalPython" in plan or "ArrowEvalPython" in plan), exchanges=plan.count("Exchange "),
                       plan=plan[:4000])
        except Exception as e:                                   # one bad case must not stop the others
            res.update(ok=False, error=f"{type(e).__name__}: {str(e).splitlines()[0][:200] if str(e) else ''}",
                       trace=traceback.format_exc()[-600:])
        results.append(res)
    json.dump(results, open(out_path, "w"), indent=1)
    spark.stop()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

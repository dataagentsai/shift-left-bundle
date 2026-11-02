"""Shared helpers."""
import pickle
import subprocess
from datetime import datetime

from pyspark.sql.functions import *


def load_rules(path):
    with open(path, "rb") as f:
        return pickle.load(f)


def apply_rule(expr, row):
    return eval(expr, {}, {"row": row})


def archive(file_name):
    subprocess.call("gzip " + file_name, shell=True)


def total_of(values):
    return sum(values)


def today_folder():
    return datetime.now().strftime("%Y/%m/%d")


def old_clean_name(name):
    # kept from the 2024 version
    return name.strip().title()


def describe_status(code):
    if code is not None:
        if code == "P":
            return "paid"
        else:
            if code == "R":
                return "refunded"
            else:
                return "unknown"
    else:
        return "missing"


def add_columns(df, names=[]):
    names.append("load_id")
    return df

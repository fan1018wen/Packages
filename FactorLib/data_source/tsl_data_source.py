"""Python调用天软的封装"""

import pandas as pd
import numpy as np
import TSLPy3 as tsl
from FactorLib.utils.tool_funcs import tradecode_to_tslcode, tslcode_to_tradecode
from FactorLib.utils.TSDataParser import *
from functools import reduce, partial


_ashare = "'上证A股;深证A股;创业板;中小企业板'"


def _gstr_from_func(func_name, func_args):
    func_str = "data := {func_name}({args}); return data;".format(func_name=func_name, args=",".join(func_args))
    return func_str


def CsQuery(field_dict, end_date, bk_name=_ashare, stock_list=None, condition="1"):
    """对天软Query函数的封装
    """
    if stock_list is None:
        stock_list = "''"
    else:
        stock_list = "'%s'" % ";".join(map(tradecode_to_tslcode, stock_list))
    encode_date = tsl.EncodeDate(end_date.year, end_date.month, end_date.day)
    func_name = "Query"
    func_args = [bk_name, stock_list, condition, "''"] + list(reduce(lambda x, y: x+y, field_dict.items()))
    script_str = _gstr_from_func(func_name, func_args)
    data = tsl.RemoteExecute(script_str, {'CurrentDate': encode_date})
    df = parse2DArray(data, column_decode=['IDs'])
    df['IDs'] = df['IDs'].apply(tslcode_to_tradecode)
    df['date'] = end_date
    return df.set_index(['date', 'IDs'])


def partialCsQueryFunc(*args, **kwargs):
    """CsQuery的偏函数"""
    return partial(CsQuery, *args, **kwargs)


if __name__ == '__main__':
    pass
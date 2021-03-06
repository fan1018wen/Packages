# coding: utf-8

"""生成股票列表"""
from ..data_source.base_data_source_h5 import data_source
from ..utils.tool_funcs import parse_industry
import pandas as pd


def typical(factor, name, direction=None, industry_neutral=True, benchmark=None, industry_name='中信一级', prc=0.05,
            top=None, **kwargs):
    """给定因子数据生成股票列表
    Paramters
    =========================
    factor_data: DataFrame(index:[date,IDs],factor1,factor2...)
    """
    factor_data = factor.reset_index()
    if prc is not None:
        prc = 1 - prc if (direction == 1 or direction is None) else prc
    if industry_neutral:
        industry_str = parse_industry(industry_name)

        all_ids = factor_data['IDs'].unique().tolist()
        all_dates = pd.DatetimeIndex(factor_data['date'].unique()).tolist()

        # 个股的行业信息与因子数据匹配
        industry_info = data_source.sector.get_stock_industry_info(
            all_ids, industry=industry_name, dates=all_dates).reset_index()
        factor_data = pd.merge(factor_data, industry_info, how='left')
        if prc is not None:
            quantile_per_industry = factor_data.groupby(['date', industry_str])[name].quantile(prc)
            quantile_per_industry.name = 'quantile_value'
            factor_data = factor_data.join(quantile_per_industry, on=['date', industry_str], how='left')

            # 股票选择，stocks=DataFrame[日期 IDs 因子值 行业 行业分位数]
            if direction == 1:
                stocks = factor_data[factor_data[name] >= factor_data['quantile_value']]
            else:
                stocks = factor_data[factor_data[name] <= factor_data['quantile_value']]
        else:
            ascending = True if direction == -1 else False
            stocks = factor_data.sort_values(name, ascending=ascending).groupby(['date', industry_str]).head(top)
        # 配置权重
        benchmark_weight = data_source.sector.get_index_industry_weight(
            benchmark, industry_name=industry_name, dates=all_dates)  # 基准指数的行业权重
        if kwargs.get('indu_weight', None):
            user_weight = pd.Series(kwargs.get('indu_weight').__dict__, name=benchmark_weight.name)
            user_weight.index.name = industry_str
            a = benchmark_weight.reset_index(level=0, drop=True)
            a.update(user_weight)
            benchmark_weight = pd.Series(a.values, index=benchmark_weight.index, name=benchmark_weight.name)
        stock_counts_per_industry = stocks.groupby(['date', industry_str])['IDs'].count()
        weight = (benchmark_weight / stock_counts_per_industry).rename('Weight')
        stocks = stocks.join(weight, on=['date', industry_str], how='left').set_index(['date', 'IDs'])[['Weight']]
        stocks.dropna(inplace=True)
        sum_weight = stocks.groupby(level=0)['Weight'].sum()
        stocks['Weight'] = stocks['Weight'] / sum_weight
    else:
        if prc is not None:
            quantile_per_date = factor_data.groupby('date')[name].quantile(prc)
            quantile_per_date.name = 'quantile_value'
            factor_data = factor_data.join(quantile_per_date, on='date', how='left')

            # 股票选择，stocks=DataFrame[日期 IDs 因子值 分位数]
            if direction == 1:
                stocks = factor_data[factor_data[name] >= factor_data['quantile_value']]
            else:
                stocks = factor_data[factor_data[name] <= factor_data['quantile_value']]
        else:
            ascending = True if direction == -1 else False
            stocks = factor_data.sort_values(name, ascending=ascending).groupby('date').head(top)
        stock_counts_per_date = stocks.groupby('date')['IDs'].count()
        stocks = stocks.join(1 / stock_counts_per_date.rename('Weight'), on='date').set_index(['date', 'IDs'])
    return stocks[['Weight']]


FuncList = {'typical': typical}
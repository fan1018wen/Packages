# coding: utf-8
"""组合归因分析"""

import pandas as pd
import numpy as np
import TSLPy3 as tsl
from fastcache import clru_cache
from .riskmodel_data_source import RiskDataSource
from ..data_source.base_data_source_h5 import data_source
from ..factor_performance.analyzer import Analyzer
from ..utils.tool_funcs import uqercode_to_windcode, windcode_to_tslcode
from ..data_source.base_data_source_h5 import tc
from fastcache import clru_cache


class RiskExposureAnalyzer(object):
    """
    风险因子的暴露分析框架,提供时间截面上风险暴露计算、图示等。
    行业分类可以自定义，通过h5数据源提取；风险因子除了BARRA风险因子之外也提供自定义功能。
    """
    def __init__(self, barra_datasource='xy', industry=None, risk_factors=None, stocks=None, benchmark=None):
        """
        Paramters:
        ==========
        barra_datasource: str
            BARRA风险数据源， 默认为'xy'
        industry: str
            行业分类，默认为None, 以BARRA模型中的行业因子替代。
        risk_factors: list-like
            风险因子，默认为None
        stocks: DataFrame
            股票持仓 DataFrame(index:[date, IDs], columns:[Weight])
        """
        self.barra_name = barra_datasource
        self.barra_ds = RiskDataSource(self.barra_name)
        self.industry = industry
        self.risk_factors = risk_factors
        self.stock_positions = stocks
        self.benchmark = benchmark
        self.barra_data = {}
        self.industry_data = {}
        self.risk_factors_data = {}

    @classmethod
    def from_df(cls, df, **kwargs):
        """
        从DataFrame导入股票持仓，返回类实例
        """
        return cls(stocks=df, **kwargs)

    @classmethod
    def from_csv(cls, csv_path, **kwargs):
        """
        从csv文件中导入股票持仓，返回类实例 \n
        csv文件的格式：日期  代码(wind格式)  权重
        """
        with open(csv_path) as f:
            stocks = pd.read_csv(f, header=0, index_col=None, parse_dates=['date'],
                                 converters={'IDs': lambda x: x[:6]})
        stocks = stocks.set_index(['date', 'IDs'])
        return cls(stocks=stocks, **kwargs)

    def _load_data(self, dates):
        """
        加载风险数据,风险数据包括BARRA风险因子，行业因子，自定义风险因子
        """
        old_dates = list(set(dates).intersection(set(self.barra_data.keys())))
        new_dates = list(set(dates).difference(set(old_dates)))
        old_barra_data = new_barra_data = pd.DataFrame()
        old_industry_data = new_industry_data = pd.DataFrame()
        old_riskfactors_data = new_risk_data = pd.DataFrame()
        if old_dates:
            old_barra_data = pd.concat([self.barra_data[x] for x in old_dates])
            old_industry_data = pd.concat([self.industry_data[x] for x in old_dates])
            if self.risk_factors is not None:
                old_riskfactors_data = pd.concat([self.risk_factors_data[x] for x in old_dates])
        if new_dates:
            new_barra_data = self.barra_ds.load_factors(factor_names='STYLE', dates=new_dates)
            if self.industry is not None:
                new_industry_data = data_source.sector.get_industry_dummy(ids=None, dates=new_dates, drop_first=False)
            else:
                new_industry_data = self.barra_ds.load_industry(ids=None, dates=new_dates)
            if self.risk_factors is not None:
                new_risk_data = data_source.h5DB.load_factors(self.risk_factors, dates=new_dates)
            for d in new_dates:
                self.barra_data[d] = new_barra_data.loc[[pd.to_datetime(d)]]
                self.industry_data[d] = new_industry_data.loc[[pd.to_datetime(d)]]
                if self.risk_factors is not None:
                    self.risk_factors_data[d] = new_risk_data.loc[[pd.to_datetime(d)]]
        barra_data = pd.concat([old_barra_data, new_barra_data]).sort_index()
        industry_data = pd.concat([old_industry_data, new_industry_data]).sort_index()
        if self.risk_factors is not None:
            risk_data = pd.concat([old_riskfactors_data, new_risk_data]).sort_index()
        else:
            risk_data = None
        return barra_data, industry_data, risk_data

    def _cal_risk_of_bchmrk(self, dates):
        """
        计算基准指数的风险因子值，若无基准指数则以零
        """
        barra, indus, risk_factor = self._load_data(dates)
        barra_b = pd.DataFrame(np.zeros((len(dates), len(barra.columns))), index=dates, columns=barra.columns)
        indus_b = pd.DataFrame(np.zeros((len(dates), len(indus.columns))), index=dates, columns=indus.columns)
        if risk_factor is not None:
            riskfactor_b = pd.DataFrame(np.zeros((len(dates), len(risk_factor.columns))), index=dates, columns=risk_factor.columns)
        else:
            riskfactor_b = None
        if self.benchmark is not None:
            weight_bchmrk = data_source.sector.get_index_weight(ids=self.benchmark, dates=dates)
            for d in dates:
                idata, iweight = barra.loc[d].align(weight_bchmrk.loc[d], join='right', axis=0)
                barra_b.loc[d] = idata.mul(iweight.iloc[:, 0], axis='index').sum()

                iindu, iweight = indus.loc[d].align(weight_bchmrk.loc[d], join='right', axis=0)
                indus_b.loc[d] = iindu.mul(iweight.iloc[:, 0], axis='index').sum()

                if risk_factor is not None:
                    irisk, iweight = indus.loc[d].align(weight_bchmrk.loc[d], join='right', axis=0)
                    riskfactor_b.loc[d] = irisk.mul(iweight.iloc[:, 0], axis='index').sum()
        return barra_b, indus_b, riskfactor_b

    def cal_risk_of_portfolio(self, dates):
        """
        计算组合的风险因子值
        """
        barra, indus, risk_factor = self._load_data(dates)
        barra_p = pd.DataFrame(np.zeros((len(dates), len(barra.columns))), index=dates, columns=barra.columns)
        indus_p = pd.DataFrame(np.zeros((len(dates), len(indus.columns))), index=dates, columns=indus.columns)
        if risk_factor is not None:
            riskfactor_p = pd.DataFrame(np.zeros((len(dates), len(risk_factor.columns))), index=dates, columns=risk_factor.columns)
        else:
            riskfactor_p = None
        for d in dates:
            idata, iweight = barra.loc[d].align(self.stock_positions.loc[pd.to_datetime(d)], join='right', axis=0)
            barra_p.loc[d] = idata.mul(iweight.iloc[:, 0], axis='index').sum()

            iindu, iweight = indus.loc[d].align(self.stock_positions.loc[pd.to_datetime(d)], join='right', axis=0)
            indus_p.loc[d] = iindu.mul(iweight.iloc[:, 0], axis='index').sum()

            if risk_factor is not None:
                irisk, iweight = indus.loc[d].align(self.stock_positions.loc[pd.to_datetime(d)], join='right', axis=0)
                riskfactor_p.loc[d] = irisk.mul(iweight.iloc[:, 0], axis='index').sum()
        return barra_p, indus_p, riskfactor_p

    @clru_cache()
    def cal_singledate_expo(self, date):
        """
        计算单期因子暴露分析
        """
        date = [date]
        return self.cal_multidates_expo(date)

    def cal_multidates_expo(self, dates):
        """
        计算多期风险暴露。\n

        Returns:
        ========
        因子暴露数据结构：
        barra_expo: DataFrame
            DataFrame(index:[date style_name], columns:[portfolio benchmark expo])
        indus_expo: DataFrame
            DataFrame(index:[date industry_name], columns:[portfolio benchmark expo])
        risk_expo: DataFrame
            DataFrame(index:[date  riskfactor_name], columns:[portfolio benchmark expo])
        """
        max_date = self.barra_ds.max_date_of_factor
        dates = dates[dates <= pd.to_datetime(max_date)]
        if len(dates) == 0:
            return None, None, None

        risk_b = self._cal_risk_of_bchmrk(dates)
        risk_p = self.cal_risk_of_portfolio(dates)

        # BARRA风险
        barra_expo = pd.concat([risk_p[0].stack(), risk_b[0].stack()], axis=1, ignore_index=True)
        barra_expo.index.names = ['date', 'barra_style']
        barra_expo.columns = ['portfolio', 'benchmark']
        barra_expo['expo'] = barra_expo['portfolio'] - barra_expo['benchmark']

        # 行业风险
        indus_expo = pd.concat([risk_p[1].stack(), risk_b[1].stack()], axis=1, ignore_index=True)
        indus_expo.index.names = ['date', 'industry']
        indus_expo.columns = ['portfolio', 'benchmark']
        indus_expo['expo'] = indus_expo['portfolio'] - indus_expo['benchmark']

        # 自定义风险
        if risk_p[2] is not None:
            risk_expo = pd.concat([risk_p[2].stack(), risk_b[2].stack()], axis=1, ignore_index=True)
            risk_expo.index.names = ['date', 'risk_factor']
            risk_expo.columns = ['portfolio', 'benchmark']
            risk_expo['expo'] = risk_expo['portfolio'] - risk_expo['benchmark']
        else:
            risk_expo = None
        return barra_expo, indus_expo, risk_expo


class RiskModelAttribution(object):
    """
    风险模型的收益归因分析
    已知组合的主动暴露(风格暴露和行业暴露)，把组合的收益率归因到因子上去
    """
    def __init__(self, ret_ptf, style_expo, industry_expo, bchmrk_name='000905', barra_ds='xy'):
        self.ret_ptf = ret_ptf                                                # 组合日频收益率
        self.style_of_ptf = style_expo['portfolio'].unstack()                 # 组合风格暴露
        self.style_expo = style_expo['expo'].unstack()                        # 风格主动暴露
        self.style_of_bch = style_expo['benchmark'].unstack()                 # 基准风格暴露

        self.industry_of_ptf = industry_expo['portfolio'].unstack()           # 组合行业暴露
        self.industry_of_bch = industry_expo['benchmark'].unstack()           # 基准行业暴露
        self.industry_expo = industry_expo['expo'].unstack()                  # 行业主动暴露
        self.bchmrk = bchmrk_name                                             # 业绩基准
        self.barra_datasource = RiskDataSource(barra_ds)                      # Barra数据源
        self._prepare_data()

    def _prepare_data(self):
        """
        准备数据
        """
        self.expo = pd.concat([self.style_expo, self.industry_expo], axis=1)
        # 日期
        self.all_dates = self.expo.index.get_level_values(0).unique().tolist()

        # 风险因子收益率
        self.factor_ret = self.barra_datasource.load_factor_return(factor_name=list(self.expo.columns),
                                                                   dates=self.all_dates)
        # 基准日收益率
        self.ret_bch = data_source.load_factor('daily_returns_%', '/indexprices/', dates=self.all_dates,
                                               ids=[self.bchmrk]).reset_index(level=1, drop=True)['daily_returns_%'] / 100
        # 基准超额收益率
        self.ret_active = self.ret_ptf - self.ret_bch

    @property
    def active_attributed_ret(self):
        """
        主动归因收益率
        组合的主动暴露 * 因子日收益率
        """
        return self.expo * self.factor_ret

    def range_attribute(self, start_date=None, end_date=None):
        """
        在某个时间范围内进行业绩归因
        """
        if start_date is None:
            start_date = self.all_dates[0]
        else:
            start_date = pd.to_datetime(start_date)

        if end_date is None:
            end_date = self.all_dates[-1]
        else:
            end_date = pd.to_datetime(end_date)

        attr_ret_active = self.active_attributed_ret.loc[start_date:end_date, :]
        ptf_ret_active = self.ret_active.loc[start_date:end_date]
        u_ret = ptf_ret_active - attr_ret_active.sum(axis=1)
        ptf_ret_active_final = (1.0 + ptf_ret_active).prod() - 1.0
        bchmrk_ret_final = (1.0 + self.ret_bch).prod() - 1.0
        u_ret_final = (1.0 + u_ret).prod() - 1.0

        attribution = ptf_ret_active_final - (1.0 + (-1.0 * attr_ret_active.sub(ptf_ret_active, axis='index'))).prod() + 1
        cross = ptf_ret_active_final - u_ret_final - attribution.sum()      # 交叉项
        weight = attribution.abs() / attribution.abs().sum() * cross
        attribution = attribution + weight
        attribution['specific'] = u_ret_final
        attribution['benchmark_ret'] = bchmrk_ret_final
        attribution['total_active_ret'] = ptf_ret_active_final
        return attribution


def create_trade_to_attr(trades, dividends, start_date, end_date):
    trades['截止日'] = pd.DatetimeIndex(pd.DatetimeIndex(trades['trading_datetime']).date)
    trades['成交金额'] = trades.eval("last_price * last_quantity - transaction_cost")
    trades['动作'] = trades['side'].map({'BUY': 0, 'SELL': 1})
    trades['代码'] = trades['order_book_ids'].apply(uqercode_to_windcode)

    dividends['截止日'] = pd.DatetimeIndex(pd.DatetimeIndex(dividends['trading_date']).date)
    dividends['成交金额'] = dividends['dividends']
    dividends['动作'] = 2
    dividends['代码'] = dividends['order_book_id'].apply(uqercode_to_windcode)

    new = trades[['截止日', '成交金额', '动作', '代码']].append(dividends[['截止日', '成交金额', '动作', '代码']])
    new.reset_index(drop=True, inplace=True)
    new = new[new['截止日'] >= start_date & new['截止日'] <= end_date]
    new['方向'] = 1
    return new


def create_portfolio_to_attr(stock_positions, start_date, end_date):
    new = stock_positions[['market_value', 'order_book_id']].reset_index()
    new.rename(columns={'date': '截止日', 'order_book_id': '代码', 'market_value': '市值'}, inplace=True)
    new['代码'] = new['代码'].apply(uqercode_to_windcode)
    new['方向'] = 1
    return new[(new['截止日'] >= start_date) & (new['截止日'] <= end_date)]


def create_asset_allocation(positions, start_date, end_date):
    new = positions[['market_value', 'total_value']].reset_index()
    new['total_value'] = np.where(new['market_value'] > new['total_value'], new['market_value'], new['total_value'])
    new['现金市值'] = new['total_value'] - new['market_value']
    new.rename(columns={'date': '截止日', 'total_value': '资产净值'}, inplace=True)
    return new[(new['截止日'] >= start_date) & (new['截止日'] <= end_date)][['截止日', '现金市值', '资产净值']]


@clru_cache()
def encode_date(year, month, day):
    return tsl.EncodeDate(year, month, day)

# def tostry(data):
#     ret =""
#     if isinstance(data,(int,float)):
#         ret = "{0}".format(data)
#     elif isinstance(data, str):
#         ret = "\"{0}\"".format(data)
#     elif isinstance(data, list):
#         lendata = len(data)
#         ret += "["
#         for i in range(lendata):
#             ret += tostry(data[i])
#             if i<(lendata-1):
#                 ret += ","
#         ret +=']'
#     elif isinstance(data, tuple):
#         lendata = len(data)
#         ret += "("
#         for i in range(lendata):
#             ret += tostry(data[i])
#         if i < (lendata - 1):
#             ret += ","
#         ret += ')'
#         elif isinstance(data, (dict)):
#         it = 0
#         lendata = len(data)
#         ret += "{"
#         for i in data:
#             ret += tostry(i) + ":" + tostry(data[i])
#         it += 1
#         if it < lendata:
#             ret += ","
#         ret += "}"
#         elif isinstance(data, (bytes)):
#         ret += data.decode('gbk')
#         else:
#         ret = "{0}".format(data)


class TSLBrinsonAttribution(object):
    """
    基于TSL客户端的Brinson风险归因

    Brinson归因需要的源数据包括交易记录、持仓明细和资产配置明细。
    交易记录的数据格式：pd.DataFrame
        ---------------------------------------------
           截止日   |  代码  |  方向  | 动作 | 成交金额
        ---------------------------------------------
        2017-12-01 | 000001 |  1    |    1  |  10000
        ---------------------------------------------
    持仓明细的数据格式 : pd.DataFrame
        ---------------------------------------------
           截止日  |
    """

    def __init__(self, trades, portfolio, asset, benchmark):
        self.trades = trades
        self.portfolio = portfolio
        self.asset = asset
        self.benchmark = benchmark
        self.start_date = portfolio['截止日'].unique()[1]
        self.end_date = portfolio['截止日'].unique()[-1]

    @classmethod
    def from_analyzer(cls, analyzer_pth, benchmark, start_date, end_date):
        """
        从某个跟踪组合中提取归因所需的数据
        """
        ana = Analyzer(analyzer_pth, benchmark)
        trades = ana.table['trades']
        positions = ana.table['stock_positions']
        portfolio = ana.table['portfolio']
        dividends = ana.get_dividends()

        start_date = tc.tradeDayOffset(start_date, -1)
        trades_to_attr = create_trade_to_attr(trades, dividends, start_date, end_date)
        trades_to_attr['代码'] = trades_to_attr['代码'].apply(windcode_to_tslcode)
        trades_to_attr['截止日'] = trades_to_attr['截止日'].apply(lambda x: encode_date(x.year, x.month, x.day))
        portfolio_to_attr = create_portfolio_to_attr(positions, start_date, end_date)
        portfolio_to_attr['代码'] = portfolio_to_attr['代码'].apply(windcode_to_tslcode)
        portfolio_to_attr['截止日'] = portfolio_to_attr['截止日'].apply(lambda x: encode_date(x.year, x.month, x.day))
        asset_to_attr = create_asset_allocation(portfolio, start_date, end_date)
        asset_to_attr['代码'] = asset_to_attr['代码'].apply(windcode_to_tslcode)
        asset_to_attr['截止日'] = asset_to_attr['截止日'].apply(lambda x: encode_date(x.year, x.month, x.day))

        return cls.__init__(trades_to_attr, portfolio_to_attr, asset_to_attr, benchmark)

    def start(self):
        """开始归因"""
        trades = self.trades.rename(columns=lambda x: x.encode("GBK")).to_dict('record')
        portfolio = self.portfolio.rename(columns=lambda x: x.encode("GBK")).to_dict('record')
        asset = self.asset.rename(columns=lambda x: x.encode("GBK")).to_dict('record')

        start = int(self.start_date.strftime("%Y%m%d"))
        end = int(self.end_date.strftime("%Y%m%d"))

        print("正在归因...")
        res = tsl.RemoteCallFunc("BrinsonAttr", [start, end, self.benchmark, trades, portfolio, asset], {})
        print("归因结束...")


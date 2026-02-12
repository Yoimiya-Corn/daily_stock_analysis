import type React from 'react';
import { useState, useEffect } from 'react';
import type { MarketRecommendationsResponse, RecommendationItem } from '../../types/analysis';
import { marketApi } from '../../api/market';
import { Card } from '../common';

/** 涨跌幅颜色 */
const getChangeColor = (pct: number): string => {
  if (pct > 0) return '#00ff88';
  if (pct < 0) return '#ff4466';
  return 'var(--text-muted)';
};

/** 单只股票行 */
const StockRow: React.FC<{ item: RecommendationItem; index: number }> = ({ item, index }) => (
  <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-elevated border border-white/5 hover:border-white/10 transition-colors">
    <span className="text-xs text-muted w-5 text-center font-mono">{index + 1}</span>
    <div className="flex-1 min-w-0">
      <div className="flex items-baseline gap-2">
        <span className="text-sm font-medium text-white truncate">{item.name}</span>
        <span className="text-xs text-muted font-mono">{item.code}</span>
      </div>
      {item.reason && (
        <p className="text-xs text-muted mt-0.5 truncate">{item.reason}</p>
      )}
    </div>
    <div className="text-right flex-shrink-0">
      <div className="text-sm font-mono text-white">{item.price.toFixed(2)}</div>
      <div
        className="text-xs font-mono font-medium"
        style={{ color: getChangeColor(item.changePct) }}
      >
        {item.changePct > 0 ? '+' : ''}{item.changePct.toFixed(2)}%
      </div>
    </div>
  </div>
);

/** 股票列表区块 */
const StockSection: React.FC<{
  label: string;
  tag: string;
  tagColor: string;
  items: RecommendationItem[];
}> = ({ label, tag, tagColor, items }) => (
  <div>
    <div className="flex items-center gap-2 mb-2">
      <span
        className="text-xs font-bold px-1.5 py-0.5 rounded"
        style={{ background: `${tagColor}20`, color: tagColor }}
      >
        {tag}
      </span>
      <span className="text-xs text-muted">{label}</span>
      <span className="text-xs text-muted">({items.length})</span>
    </div>
    {items.length > 0 ? (
      <div className="flex flex-col gap-1.5">
        {items.map((item) => (
          <StockRow key={item.code} item={item} index={items.indexOf(item)} />
        ))}
      </div>
    ) : (
      <div className="text-xs text-muted px-3 py-4 text-center bg-elevated rounded-lg border border-white/5">
        暂无推荐
      </div>
    )}
  </div>
);

/**
 * 全市场选股推荐组件
 */
export const MarketRecommendations: React.FC = () => {
  const [data, setData] = useState<MarketRecommendationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    const fetch = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await marketApi.getRecommendations();
        if (!cancelled) {
          setData(result);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : '加载失败');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    fetch();
    return () => { cancelled = true; };
  }, []);

  if (loading) {
    return (
      <Card variant="bordered" padding="md">
        <div className="flex flex-col items-center py-8">
          <div className="w-8 h-8 border-2 border-cyan/20 border-t-cyan rounded-full animate-spin" />
          <p className="mt-3 text-secondary text-sm">正在筛选全市场股票...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card variant="bordered" padding="md">
        <div className="text-center py-6">
          <p className="text-sm text-danger">{error}</p>
          <button
            type="button"
            className="mt-2 text-xs text-cyan hover:underline"
            onClick={() => window.location.reload()}
          >
            重新加载
          </button>
        </div>
      </Card>
    );
  }

  if (!data) return null;

  return (
    <Card variant="bordered" padding="md">
      <div className="mb-4 flex items-baseline justify-between">
        <div className="flex items-baseline gap-2">
          <span className="label-uppercase">MARKET PICKS</span>
          <h3 className="text-base font-semibold text-white">全市场选股推荐</h3>
        </div>
        {data.updatedAt && (
          <span className="text-xs text-muted">{data.updatedAt}</span>
        )}
      </div>
      <div className="flex flex-col gap-4">
        <StockSection
          label="建议买入"
          tag="BUY"
          tagColor="#00ff88"
          items={data.buy}
        />
        <StockSection
          label="建议观察"
          tag="WATCH"
          tagColor="#ffaa00"
          items={data.watch}
        />
      </div>
    </Card>
  );
};

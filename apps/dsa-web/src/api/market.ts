import apiClient from './index';
import { toCamelCase } from './utils';
import type { MarketRecommendationsResponse } from '../types/analysis';

export const marketApi = {
  /**
   * 获取全市场选股推荐
   */
  getRecommendations: async (): Promise<MarketRecommendationsResponse> => {
    const response = await apiClient.get<Record<string, unknown>>(
      '/api/v1/market/recommendations'
    );
    return toCamelCase<MarketRecommendationsResponse>(response.data);
  },
};

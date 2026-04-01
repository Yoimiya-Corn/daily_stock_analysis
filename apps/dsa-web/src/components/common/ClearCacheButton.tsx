
import React, { useState } from 'react';

interface ClearCacheButtonProps {
  className?: string;
  onSuccess?: () => void;
}

export const ClearCacheButton: React.FC<ClearCacheButtonProps> = ({ className, onSuccess }) => {
  const [status, setStatus] = useState<'idle' | 'loading' | 'success' | 'error'>('idle');

  const handleClearCache = async () => {
    setStatus('loading');
    
    try {
      // 1. 清除 Service Worker 缓存
      if ('caches' in window) {
        const cacheNames = await caches.keys();
        await Promise.all(cacheNames.map(name => caches.delete(name)));
      }

      // 2. 清除 LocalStorage
      localStorage.clear();

      // 3. 清除 IndexedDB (尝试清除当前源下的所有数据库)
      if ('indexedDB' in window && typeof indexedDB.databases === 'function') {
        try {
          const dbs = await indexedDB.databases();
          await Promise.all(dbs.map(db => {
            if (db.name) {
              return new Promise<void>((resolve, reject) => {
                const request = indexedDB.deleteDatabase(db.name!);
                request.onsuccess = () => resolve();
                request.onerror = () => reject(request.error);
                request.onblocked = () => console.warn(`Delete blocked for DB: ${db.name}`);
              });
            }
            return Promise.resolve();
          }));
        } catch (e) {
          console.warn('Failed to clear IndexedDB:', e);
          // 继续执行，不阻断流程
        }
      }

      // 4. 清除 SessionStorage 并设置强制刷新标记
      sessionStorage.clear();
      // 设置一个强制刷新标记，有效期设为当前会话
      sessionStorage.setItem('FORCE_REFRESH_TIMESTAMP', Date.now().toString());

      // 5. 视觉反馈
      setStatus('success');
      
      // 延迟后刷新页面
      setTimeout(() => {
        setStatus('idle');
        if (onSuccess) {
          onSuccess();
        } else {
          window.location.reload();
        }
      }, 1000);

    } catch (error) {
      console.error('Clear cache failed:', error);
      setStatus('error');
      // 3秒后恢复
      setTimeout(() => setStatus('idle'), 3000);
    }
  };

  const getButtonText = () => {
    switch (status) {
      case 'loading': return '清除中...';
      case 'success': return '已清除';
      case 'error': return '清除失败，请重试';
      default: return '刷新数据';
    }
  };

  return (
    <button
      type="button"
      onClick={handleClearCache}
      disabled={status === 'loading' || status === 'success'}
      className={`
        inline-flex items-center justify-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors
        ${status === 'error' 
          ? 'bg-danger/10 text-danger hover:bg-danger/20' 
          : status === 'success'
            ? 'bg-success/10 text-success'
            : 'bg-white/5 text-secondary hover:bg-white/10 hover:text-white'
        }
        ${className || ''}
      `}
      title="清除缓存并强制刷新数据"
    >
      {status === 'loading' && (
        <svg className="w-3 h-3 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {status === 'idle' && (
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
        </svg>
      )}
      {status === 'success' && (
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M5 13l4 4L19 7" />
        </svg>
      )}
      {getButtonText()}
    </button>
  );
};

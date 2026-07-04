import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { EmptyState } from "../components/EmptyState";
import { api, apiFailureMessage } from "../lib/api";

export function SearchPage() {
  const [query, setQuery] = useState("茅台");
  const [activeQuery, setActiveQuery] = useState("茅台");
  const results = useQuery({
    queryKey: ["symbol-search", activeQuery],
    queryFn: () => api.searchSymbols(activeQuery),
    enabled: activeQuery.length > 0,
  });

  function submit(event: FormEvent) {
    event.preventDefault();
    setActiveQuery(query.trim());
  }

  return (
    <div className="page-stack search-page">
      <section className="section-head">
        <div>
          <div className="eyebrow">SYMBOL SEARCH</div>
          <h2>股票检索</h2>
          <p>检索当前首版内置符号库；后续可接入更完整的交易所证券列表。</p>
        </div>
        <form className="terminal-search" onSubmit={submit}>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入代码或公司名称" />
          <button className="terminal-button" type="submit">
            <Search size={16} />
            检索
          </button>
        </form>
      </section>

      <section className="data-panel">
        <div className="panel-head">
          <div>
            <h3>检索结果</h3>
            <span>{results.data?.length || 0} 条</span>
          </div>
        </div>
        {results.isPending ? <div className="market-empty compact">正在连接后端检索服务...</div> : null}
        {results.isError ? <EmptyState title="检索加载失败" body={apiFailureMessage(results.error, "股票检索")} /> : null}
        <div className="quote-list">
          {results.data?.map((item) => (
            <div className="quote-row" key={item.symbol}>
              <div>
                <strong>{item.name}</strong>
                <span>{item.symbol}</span>
              </div>
              <div className="quote-price">
                <strong>{item.market}</strong>
                <span>{item.currency}</span>
              </div>
            </div>
          ))}
        </div>
        {!results.isPending && !results.isError && !results.data?.length ? (
          <EmptyState title="暂无匹配结果" body="调整关键词后重新检索，页面不会展示模拟证券。" />
        ) : null}
      </section>
    </div>
  );
}

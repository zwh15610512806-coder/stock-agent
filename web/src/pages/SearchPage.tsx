import { FormEvent, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api } from "../lib/api";

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
    <div className="page-stack">
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
      </section>
    </div>
  );
}

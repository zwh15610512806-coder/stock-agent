import { FormEvent, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import {
  BarChart3,
  CalendarDays,
  CircleGauge,
  Layers,
  Menu,
  Moon,
  Search,
  Sparkles,
  TrendingUp,
  X,
} from "lucide-react";
import { AiPage } from "./pages/AiPage";
import { MacroPage } from "./pages/MacroPage";
import { MarketPage } from "./pages/MarketPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { SearchPage } from "./pages/SearchPage";
import { StockPage } from "./pages/StockPage";
import { StocksPage } from "./pages/StocksPage";

const navItems = [
  { to: "/market", label: "市场", icon: BarChart3 },
  { to: "/macro", label: "宏观", icon: CircleGauge },
  { to: "/stocks", label: "选股", icon: TrendingUp },
  { to: "/portfolio", label: "我的持仓", icon: Layers },
  { to: "/ai", label: "AI研报", icon: Sparkles },
];

export function App() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [isMenuOpen, setIsMenuOpen] = useState(false);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    navigate(`/search${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`);
  };

  return (
    <div className="xirang-shell">
      <header className="xirang-header">
        <div className="xirang-header-inner">
          <button
            type="button"
            className="xirang-icon-button mobile-menu-button"
            aria-label={isMenuOpen ? "关闭菜单" : "打开菜单"}
            onClick={() => setIsMenuOpen((value) => !value)}
          >
            {isMenuOpen ? <X size={22} /> : <Menu size={22} />}
          </button>

          <NavLink to="/market" className="xirang-brand" aria-label="裕见投研">
            <TrendingUp size={23} />
            <span>裕见投研</span>
          </NavLink>

          <nav className="xirang-nav" aria-label="主导航">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} className={({ isActive }) => `xirang-nav-link${isActive ? " active" : ""}`}>
                <item.icon size={16} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="xirang-actions">
            <form className="xirang-search" onSubmit={submitSearch}>
              <Search size={15} />
              <input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="搜索股票、持仓、标签..."
                aria-label="全局搜索"
              />
              <button type="submit" aria-label="搜索">
                搜索
              </button>
              <kbd>⌘ K</kbd>
            </form>
            <button type="button" className="xirang-tool-button">
              <CalendarDays size={16} />
              时光机
            </button>
            <button type="button" className="xirang-icon-button" aria-label="切换主题">
              <Moon size={17} />
            </button>
          </div>
        </div>

        {isMenuOpen ? (
          <nav className="xirang-mobile-nav" aria-label="移动导航">
            {navItems.map((item) => (
              <NavLink key={item.to} to={item.to} onClick={() => setIsMenuOpen(false)}>
                <item.icon size={16} />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>
        ) : null}
      </header>

      <main className="xirang-main">
        <Routes>
          <Route path="/" element={<Navigate to="/market" replace />} />
          <Route path="/market" element={<MarketPage />} />
          <Route path="/macro" element={<MacroPage />} />
          <Route path="/stocks" element={<StocksPage />} />
          <Route path="/stock" element={<StockPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/ai" element={<AiPage />} />
          <Route path="/search" element={<SearchPage />} />
        </Routes>
      </main>

      <NavLink to="/portfolio" className="portfolio-sandbox-link">
        <Layers size={17} />
        组合沙箱
      </NavLink>

      <footer className="xirang-footer">
        <div className="xirang-footer-grid">
          <div className="xirang-footer-brand">
            <NavLink to="/market" className="xirang-brand">
              <TrendingUp size={22} />
              <span>裕见投研</span>
            </NavLink>
            <p>面向股票、持仓与 AI 研究的本地投研分析平台。</p>
          </div>
          <FooterColumn
            title="快速链接"
            links={[
              { label: "市场全景", to: "/market" },
              { label: "股票分析", to: "/stocks" },
              { label: "我的持仓", to: "/portfolio" },
            ]}
          />
          <FooterColumn
            title="资源"
            links={[
              { label: "真实数据源", to: "/market" },
              { label: "AI 研报", to: "/ai" },
            ]}
          />
          <div className="xirang-footer-column">
            <h3>联系</h3>
            <span>本地研究终端</span>
            <span>数据来源：akshare / Yahoo / Tencent / THS</span>
            <span>仅供研究，不构成投资建议</span>
          </div>
        </div>
        <div className="xirang-footer-bottom">
          <span>© 2026 裕见投研</span>
          <span>
            <Sparkles size={13} /> 免费延迟行情，仅供研究
          </span>
        </div>
      </footer>
    </div>
  );
}

function FooterColumn({ title, links }: { title: string; links: Array<{ label: string; to: string }> }) {
  return (
    <div className="xirang-footer-column">
      <h3>{title}</h3>
      {links.map((link) => (
        <NavLink key={link.to} to={link.to}>
          {link.label}
        </NavLink>
      ))}
    </div>
  );
}

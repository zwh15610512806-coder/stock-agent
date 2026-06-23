import { FormEvent, useState } from "react";
import { Navigate, NavLink, Route, Routes, useNavigate } from "react-router-dom";
import {
  Activity,
  Bell,
  Bot,
  BriefcaseBusiness,
  CalendarDays,
  ChevronDown,
  CircleAlert,
  Database,
  FileText,
  Home,
  LineChart,
  LogOut,
  Newspaper,
  Search,
  Settings,
  ShieldAlert,
  SlidersHorizontal,
  Star,
  UserRound,
} from "lucide-react";
import { AiPage } from "./pages/AiPage";
import { MarketPage } from "./pages/MarketPage";
import { PortfolioPage } from "./pages/PortfolioPage";
import { SearchPage } from "./pages/SearchPage";
import { StockPage } from "./pages/StockPage";
import { A_SHARE_REFRESH_POLICY_LABEL } from "./lib/refresh-schedule";

const navItems = [
  { to: "/", label: "市场总览", icon: Home, end: true },
  { to: "/portfolio", label: "持仓", icon: BriefcaseBusiness },
  { to: "/stock", label: "个股", icon: LineChart },
  { to: "/ai", label: "研报", icon: FileText },
  { to: "/search", label: "新闻", icon: Newspaper },
  { to: "/search", label: "数据", icon: Database },
  { to: "/macro", label: "策略", icon: Activity },
  { to: "/ai", label: "AI 投顾", icon: Bot },
  { to: "/search", label: "自选", icon: Star },
  { to: "/portfolio", label: "预警", icon: CircleAlert },
];

export function App() {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [date, setDate] = useState("2024-06-20");
  const [view, setView] = useState("自定义视图");
  const [openMenu, setOpenMenu] = useState<"quick" | "notice" | "user" | null>(null);

  const submitSearch = (event: FormEvent) => {
    event.preventDefault();
    navigate(`/search${query.trim() ? `?q=${encodeURIComponent(query.trim())}` : ""}`);
  };

  return (
    <div className="terminal-shell pro-shell">
      <aside className="sidebar pro-sidebar">
        <div className="brand-block pro-brand">
          <div className="brand-mark">ZT</div>
          <div>
            <div className="brand-title">智投终端</div>
            <div className="brand-subtitle">ZHI TOUS TERMINAL</div>
          </div>
        </div>

        <nav className="nav-list pro-nav" aria-label="主导航">
          {navItems.map((item) => (
            <NavLink
              key={`${item.label}-${item.to}`}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link${isActive && item.end ? " active" : ""}`}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          <button type="button" className="sidebar-utility">
            <Settings size={16} />
            设置
          </button>
          <button type="button" className="sidebar-utility">
            <LogOut size={16} />
            退出
          </button>
        </div>
      </aside>

      <main className="workspace pro-workspace">
        <header className="topbar pro-topbar">
          <div className="topbar-brand">
            <h1>智投终端</h1>
            <span>专业版</span>
          </div>

          <form className="topbar-search" onSubmit={submitSearch}>
            <Search size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="搜索股票 / 指数 / 板块 / 资讯"
              aria-label="全局搜索"
            />
          </form>

          <div className="topbar-actions">
            <div className="menu-anchor">
              <button type="button" className="toolbar-button" onClick={() => setOpenMenu(openMenu === "quick" ? null : "quick")}>
                <SlidersHorizontal size={16} />
                快捷操作
                <ChevronDown size={14} />
              </button>
              {openMenu === "quick" ? (
                <div className="floating-menu">
                  <button type="button">刷新行情</button>
                  <button type="button">导入持仓</button>
                  <button type="button">生成研报</button>
                </div>
              ) : null}
            </div>

            <label className="date-control">
              <input type="date" value={date} onChange={(event) => setDate(event.target.value)} />
              <CalendarDays size={15} />
            </label>

            <select className="view-select" value={view} onChange={(event) => setView(event.target.value)} aria-label="视图选择">
              <option>自定义视图</option>
              <option>交易时段</option>
              <option>风险监控</option>
            </select>

            <div className="menu-anchor">
              <button
                type="button"
                className="icon-toolbar-button"
                aria-label="通知"
                onClick={() => setOpenMenu(openMenu === "notice" ? null : "notice")}
              >
                <Bell size={18} />
                <span className="notification-dot">12</span>
              </button>
              {openMenu === "notice" ? (
                <div className="floating-menu right-menu">
                  <strong>暂无新的真实告警</strong>
                  <span>预警中心首版仅展示本地状态。</span>
                </div>
              ) : null}
            </div>

            <div className="menu-anchor">
              <button type="button" className="user-chip" onClick={() => setOpenMenu(openMenu === "user" ? null : "user")}>
                <span className="avatar"><UserRound size={16} /></span>
                投资者Z
                <ChevronDown size={14} />
              </button>
              {openMenu === "user" ? (
                <div className="floating-menu right-menu">
                  <strong>本地研究终端</strong>
                  <span>{A_SHARE_REFRESH_POLICY_LABEL}</span>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <Routes>
          <Route path="/" element={<MarketPage />} />
          <Route path="/macro" element={<Navigate to="/" replace />} />
          <Route path="/stock" element={<StockPage />} />
          <Route path="/portfolio" element={<PortfolioPage />} />
          <Route path="/ai" element={<AiPage />} />
          <Route path="/search" element={<SearchPage />} />
        </Routes>

        <footer className="pro-footer">
          <span>数据来源：akshare / Yahoo / Tencent / LeGuLeGu / THS</span>
          <span>免责声明</span>
          <span>隐私政策</span>
          <span>服务协议</span>
          <span><ShieldAlert size={13} /> 免费延迟行情，仅供研究</span>
        </footer>
      </main>
    </div>
  );
}

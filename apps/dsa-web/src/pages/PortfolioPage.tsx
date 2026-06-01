import type React from 'react';
import { Link } from 'react-router-dom';
import { AppPage, Card, PageHeader } from '../components/common';

const PortfolioPage: React.FC = () => {
  return (
    <AppPage className="max-w-[1200px] space-y-3">
      <PageHeader
        eyebrow="Portfolio"
        title="持仓旧入口已迁移"
        description="资产初始化、资产管理和资产事件已经拆分为独立页面。"
        className="!rounded-xl !px-4 !py-3"
      />

      <section className="grid gap-3 md:grid-cols-3">
        <Card className="!rounded-xl" padding="sm">
          <p className="text-xs uppercase tracking-[0.22em] text-secondary">Step 01</p>
          <h2 className="mt-2 text-base font-semibold text-foreground">资产初始化</h2>
          <p className="mt-2 text-sm text-secondary">创建账户，录入初始资产，形成建账起点。</p>
          <Link className="btn-secondary mt-4 inline-flex !px-3 !py-1.5 !text-xs" to="/assets/init">
            前往初始化
          </Link>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <p className="text-xs uppercase tracking-[0.22em] text-secondary">Step 02</p>
          <h2 className="mt-2 text-base font-semibold text-foreground">资产管理</h2>
          <p className="mt-2 text-sm text-secondary">查看静态持仓快照，并对 R4/R5 进行页面级实时重估。</p>
          <Link className="btn-secondary mt-4 inline-flex !px-3 !py-1.5 !text-xs" to="/assets/manage">
            前往资产管理
          </Link>
        </Card>

        <Card className="!rounded-xl" padding="sm">
          <p className="text-xs uppercase tracking-[0.22em] text-secondary">Step 03</p>
          <h2 className="mt-2 text-base font-semibold text-foreground">资产事件</h2>
          <p className="mt-2 text-sm text-secondary">统一维护交易事件、资金流水和现金分红事件。</p>
          <Link className="btn-secondary mt-4 inline-flex !px-3 !py-1.5 !text-xs" to="/assets/events">
            前往资产事件
          </Link>
        </Card>
      </section>
    </AppPage>
  );
};

export default PortfolioPage;

import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import PortfolioPage from '../PortfolioPage';

function renderPortfolioPage() {
  return render(
    <MemoryRouter>
      <PortfolioPage />
    </MemoryRouter>,
  );
}

describe('PortfolioPage migration notice', () => {
  it('renders the migrated portfolio entry points', () => {
    renderPortfolioPage();

    expect(screen.getByRole('heading', { name: '持仓旧入口已迁移' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '资产初始化' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '资产管理' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: '资产事件' })).toBeInTheDocument();
  });

  it('links to the replacement portfolio pages', () => {
    renderPortfolioPage();

    expect(screen.getByRole('link', { name: '前往初始化' })).toHaveAttribute('href', '/assets/init');
    expect(screen.getByRole('link', { name: '前往资产管理' })).toHaveAttribute('href', '/assets/manage');
    expect(screen.getByRole('link', { name: '前往资产事件' })).toHaveAttribute('href', '/assets/events');
  });
});

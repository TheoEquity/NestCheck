import { AppPage, Card, EmptyState } from '../components/common';

const WatchlistPage: React.FC = () => {
  return (
    <AppPage>
      <Card className="rounded-xl">
        <EmptyState
          title="关注标的"
          description="这里将展示您关注的股票、基金，并在出现异常时提示变灯。功能即将上线。"
          className="py-20"
        />
      </Card>
    </AppPage>
  );
};

export default WatchlistPage;

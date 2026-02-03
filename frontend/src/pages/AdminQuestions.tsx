import React from 'react';
import { Typography } from 'antd';
import Layout from '../components/common/Layout';

const { Title } = Typography;

const AdminQuestions: React.FC = () => {
  return (
    <Layout>
      <Title level={2}>Manage Questions</Title>
      <p>Question management interface will be implemented in Phase 6.</p>
    </Layout>
  );
};

export default AdminQuestions;

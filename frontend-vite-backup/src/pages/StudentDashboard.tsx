import React from 'react';
import { Typography } from 'antd';
import Layout from '../components/common/Layout';

const { Title } = Typography;

const StudentDashboard: React.FC = () => {
  return (
    <Layout>
      <Title level={2}>Student Dashboard</Title>
      <p>Welcome to the SQL Learning Platform!</p>
      <p>Questions list will be displayed here (Phase 5).</p>
    </Layout>
  );
};

export default StudentDashboard;

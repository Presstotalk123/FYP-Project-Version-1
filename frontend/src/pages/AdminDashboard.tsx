import React from 'react';
import { Typography, Button } from 'antd';
import { useNavigate } from 'react-router-dom';
import Layout from '../components/common/Layout';

const { Title } = Typography;

const AdminDashboard: React.FC = () => {
  const navigate = useNavigate();

  return (
    <Layout>
      <Title level={2}>Admin Dashboard</Title>
      <p>Welcome to the administration panel!</p>
      <Button
        type="primary"
        onClick={() => navigate('/admin/questions')}
      >
        Manage Questions
      </Button>
    </Layout>
  );
};

export default AdminDashboard;

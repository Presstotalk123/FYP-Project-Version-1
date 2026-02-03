import React from 'react';
import { Layout as AntLayout, Menu, Button, Typography } from 'antd';
import { LogoutOutlined, CodeOutlined, UserOutlined, FileTextOutlined } from '@ant-design/icons';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { UserRole } from '../../types/user.types';

const { Header, Content, Sider } = AntLayout;
const { Title } = Typography;

interface LayoutProps {
  children: React.ReactNode;
}

const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { user, logout, isStaff } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  // Menu items based on role
  const menuItems = isStaff
    ? [
        {
          key: '/admin',
          icon: <FileTextOutlined />,
          label: 'Dashboard',
          onClick: () => navigate('/admin'),
        },
        {
          key: '/admin/questions',
          icon: <CodeOutlined />,
          label: 'Manage Questions',
          onClick: () => navigate('/admin/questions'),
        },
      ]
    : [
        {
          key: '/student',
          icon: <FileTextOutlined />,
          label: 'Questions',
          onClick: () => navigate('/student'),
        },
      ];

  return (
    <AntLayout style={{ minHeight: '100vh' }}>
      <Header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: '#001529',
        padding: '0 24px',
      }}>
        <Title level={4} style={{ color: 'white', margin: 0 }}>
          SQL Learning Platform
        </Title>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <span style={{ color: 'white' }}>
            <UserOutlined /> {user?.email}
          </span>
          <Button
            type="primary"
            danger
            icon={<LogoutOutlined />}
            onClick={handleLogout}
          >
            Logout
          </Button>
        </div>
      </Header>
      <AntLayout>
        <Sider width={200} style={{ background: '#fff' }}>
          <Menu
            mode="inline"
            selectedKeys={[location.pathname]}
            style={{ height: '100%', borderRight: 0 }}
            items={menuItems}
          />
        </Sider>
        <AntLayout style={{ padding: '24px' }}>
          <Content
            style={{
              background: '#fff',
              padding: 24,
              margin: 0,
              minHeight: 280,
            }}
          >
            {children}
          </Content>
        </AntLayout>
      </AntLayout>
    </AntLayout>
  );
};

export default Layout;

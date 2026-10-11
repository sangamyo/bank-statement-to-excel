import { createBrowserRouter } from 'react-router';
import { Layout } from './layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { ConvertPDF } from './pages/ConvertPDF';
import { History } from './pages/History';
import { Settings } from './pages/Settings';

export const router = createBrowserRouter([
  {
    path: '/',
    Component: Layout,
    children: [
      {
        index: true,
        Component: Dashboard,
      },
      {
        path: 'convert',
        Component: ConvertPDF,
      },
      {
        path: 'history',
        Component: History,
      },
      {
        path: 'settings',
        Component: Settings,
      },
    ],
  },
]);

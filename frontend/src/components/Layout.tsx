import { useState } from 'react';
import { LogOut, Menu as MenuIcon, Moon, Sun } from 'lucide-react';
import {
  AppBar,
  Box,
  Button,
  Chip,
  Container,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  Toolbar,
  Typography,
} from '@mui/material';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../auth/authContext';
import { CTA, ROUTES } from '../lib/constants';
import { useColorMode } from '../theme/colorModeContext';
import { BrandLogo } from './BrandLogo';
import { PageTransition } from './motion/PageTransition';
import { NlpInfoWidget } from './NlpInfoWidget';

const NAV_ITEMS = [
  { label: 'Dashboard', to: ROUTES.dashboard, end: true },
  { label: 'History', to: ROUTES.history, end: false },
];

/** Protected app shell: top nav + role badge + sign out (§4). */
export function Layout() {
  const { user, logout } = useAuth();
  const { mode, toggleMode } = useColorMode();
  const navigate = useNavigate();
  const [drawerOpen, setDrawerOpen] = useState(false);

  function handleSignOut() {
    logout();
    navigate(ROUTES.login, { replace: true });
  }

  // Linear nav: muted links, the active one simply turns bright on a soft pill.
  const navButtonSx = {
    color: 'text.secondary',
    '&:hover': { color: 'text.primary', bgcolor: 'action.hover' },
    '&.active': { color: 'text.primary', bgcolor: 'action.hover' },
  } as const;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: 'background.default' }}>
      <AppBar position="sticky">
        <Toolbar>
          <IconButton
            edge="start"
            aria-label="Open navigation"
            onClick={() => setDrawerOpen(true)}
            sx={{ mr: 1, display: { xs: 'inline-flex', md: 'none' } }}
          >
            <MenuIcon size={20} />
          </IconButton>

          <Box sx={{ mr: 4 }}>
            <BrandLogo />
          </Box>

          <Stack direction="row" spacing={1} sx={{ flexGrow: 1, display: { xs: 'none', md: 'flex' } }}>
            {NAV_ITEMS.map((item) => (
              <Button key={item.to} component={NavLink} to={item.to} end={item.end} sx={navButtonSx}>
                {item.label}
              </Button>
            ))}
          </Stack>

          <Box sx={{ flexGrow: { xs: 1, md: 0 } }} />

          <Stack direction="row" spacing={1.5} alignItems="center">
            <IconButton
              size="small"
              onClick={toggleMode}
              aria-label={mode === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
            >
              {mode === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </IconButton>
            <NlpInfoWidget />
            {user && (
              <Stack direction="row" spacing={1} alignItems="center" sx={{ display: { xs: 'none', sm: 'flex' } }}>
                <Typography variant="body2" color="text.secondary">
                  {user.fullName}
                </Typography>
                <Chip label={user.role} size="small" color="secondary" variant="outlined" />
              </Stack>
            )}
            <Button
              startIcon={<LogOut size={16} />}
              onClick={handleSignOut}
              sx={{ color: 'text.secondary', '&:hover': { color: 'text.primary' } }}
            >
              {CTA.signOut}
            </Button>
          </Stack>
        </Toolbar>
      </AppBar>

      <Drawer anchor="left" open={drawerOpen} onClose={() => setDrawerOpen(false)}>
        <Box sx={{ width: 240 }} role="presentation" onClick={() => setDrawerOpen(false)}>
          <Box sx={{ p: 2 }}>
            <BrandLogo />
          </Box>
          <Divider />
          <List>
            {NAV_ITEMS.map((item) => (
              <ListItem key={item.to} disablePadding>
                <ListItemButton component={NavLink} to={item.to} end={item.end}>
                  <ListItemText primary={item.label} />
                </ListItemButton>
              </ListItem>
            ))}
          </List>
        </Box>
      </Drawer>

      <Container maxWidth="lg" sx={{ py: 4 }}>
        <PageTransition>
          <Outlet />
        </PageTransition>
      </Container>
    </Box>
  );
}

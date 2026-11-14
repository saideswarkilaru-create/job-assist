import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'today' },
  { path: 'today', title: 'Today', loadComponent: () => import('./pages/today').then((m) => m.TodayPage) },
  { path: 'profiles', title: 'Profiles', loadComponent: () => import('./pages/profiles').then((m) => m.ProfilesPage) },
  {
    path: 'profiles/:id',
    title: 'Edit profile',
    loadComponent: () => import('./pages/profile-edit').then((m) => m.ProfileEditPage),
  },
  { path: 'sources', title: 'Companies & Sites', loadComponent: () => import('./pages/sources').then((m) => m.SourcesPage) },
  { path: 'resumes', title: 'Resumes', loadComponent: () => import('./pages/resumes').then((m) => m.ResumesPage) },
  { path: 'runs', title: 'Runs', loadComponent: () => import('./pages/runs').then((m) => m.RunsPage) },
  { path: 'settings', title: 'Settings', loadComponent: () => import('./pages/settings').then((m) => m.SettingsPage) },
  { path: 'my-details', title: 'My details', loadComponent: () => import('./pages/my-details').then((m) => m.MyDetailsPage) },
  { path: 'applications', title: 'Applications', loadComponent: () => import('./pages/applications').then((m) => m.ApplicationsPage) },
  { path: 'stats', title: 'Stats', loadComponent: () => import('./pages/stats').then((m) => m.StatsPage) },
  { path: '**', redirectTo: 'today' },
];

import React, { useState } from 'react';
import { View, StyleSheet, TouchableOpacity, Text } from 'react-native';
import { HomeScreen } from '../screens/HomeScreen';
import { AppointmentsScreen } from '../screens/AppointmentsScreen';
import { ClientsScreen } from '../screens/ClientsScreen';
import { PortfolioScreen } from '../screens/PortfolioScreen';
import { SettingsScreen } from '../screens/SettingsScreen';
import { CaptureScreen } from '../screens/CaptureScreen';
import { PaymentsScreen } from '../screens/PaymentsScreen';
import { AvailabilityScreen } from '../screens/AvailabilityScreen';
import { colors, spacing } from '../theme/colors';

type Tab = 'home' | 'appointments' | 'clients' | 'portfolio' | 'settings';
type Modal = 'capture' | 'payments' | 'availability' | null;

const TABS: { key: Tab; label: string; icon: string }[] = [
  { key: 'home',         label: 'Home',      icon: '⌂' },
  { key: 'appointments', label: 'Book',      icon: '📅' },
  { key: 'clients',      label: 'Clients',   icon: '👤' },
  { key: 'portfolio',    label: 'Portfolio', icon: '📷' },
  { key: 'settings',     label: 'Settings',  icon: '⚙' },
];

export function RootNavigator() {
  const [activeTab, setActiveTab] = useState<Tab>('home');
  const [modal, setModal] = useState<Modal>(null);

  function handleNavigate(screen: string) {
    if (screen === 'appointments' || screen === 'walkin') { setActiveTab('appointments'); return; }
    if (screen === 'capture')      { setModal('capture'); return; }
    if (screen === 'payments')     { setModal('payments'); return; }
    if (screen === 'availability') { setModal('availability'); return; }
  }

  return (
    <View style={styles.container}>
      <View style={styles.screen}>
        {activeTab === 'home'         && <HomeScreen onNavigate={handleNavigate} />}
        {activeTab === 'appointments' && <AppointmentsScreen />}
        {activeTab === 'clients'      && <ClientsScreen />}
        {activeTab === 'portfolio'    && <PortfolioScreen />}
        {activeTab === 'settings'     && <SettingsScreen />}
      </View>

      <View style={styles.tabBar}>
        {TABS.map(tab => (
          <TouchableOpacity
            key={tab.key}
            style={styles.tabItem}
            onPress={() => setActiveTab(tab.key)}
            activeOpacity={0.7}
          >
            <Text style={[styles.tabIcon, activeTab === tab.key && styles.tabIconActive]}>{tab.icon}</Text>
            <Text style={[styles.tabLabel, activeTab === tab.key && styles.tabLabelActive]}>{tab.label}</Text>
          </TouchableOpacity>
        ))}
      </View>

      {/* Full-screen overlay modals with visible close button */}
      {modal !== null && (
        <View style={StyleSheet.absoluteFill}>
          {/* Close bar */}
          <TouchableOpacity style={styles.closeBar} onPress={() => setModal(null)}>
            <Text style={styles.closeBarText}>Done</Text>
          </TouchableOpacity>

          {modal === 'capture'      && <CaptureScreen onDone={() => setModal(null)} />}
          {modal === 'payments'     && <PaymentsScreen />}
          {modal === 'availability' && <AvailabilityScreen />}
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  screen: { flex: 1 },
  tabBar: {
    flexDirection: 'row',
    backgroundColor: colors.surface,
    borderTopWidth: 1,
    borderTopColor: colors.border,
    paddingBottom: 8,
    paddingTop: 4,
  },
  tabItem: {
    flex: 1, alignItems: 'center', justifyContent: 'center',
    paddingVertical: 6, minHeight: 52, gap: 2,
  },
  tabIcon: { fontSize: 20, color: colors.textDim },
  tabIconActive: { color: colors.primary },
  tabLabel: { fontSize: 10, color: colors.textDim, fontWeight: '500' },
  tabLabelActive: { color: colors.primary, fontWeight: '700' },
  closeBar: {
    backgroundColor: colors.surface,
    borderBottomWidth: 1,
    borderBottomColor: colors.border,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.sm,
    alignItems: 'flex-end',
    minHeight: 48,
    justifyContent: 'center',
    zIndex: 10,
  },
  closeBarText: { color: colors.primary, fontWeight: '700', fontSize: 15 },
});

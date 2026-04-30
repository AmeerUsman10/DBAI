import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, RefreshControl } from 'react-native';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import { getAppointmentsForDate, getDailyTotal, getWeeklyTotals } from '../database/db';
import type { Appointment } from '../types';

const todayStr = () => new Date().toISOString().split('T')[0];

interface Props {
  onNavigate: (screen: string) => void;
}

export function HomeScreen({ onNavigate }: Props) {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('home'));
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [dailyTotal, setDailyTotal] = useState(0);
  const [weeklyTotals, setWeeklyTotals] = useState<{ date: string; total: number }[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!barber) return;
    const today = todayStr();
    const [appts, total, weekly] = await Promise.all([
      getAppointmentsForDate(barber.id, today),
      getDailyTotal(barber.id, today),
      isAdvanced ? getWeeklyTotals(barber.id) : Promise.resolve([]),
    ]);
    setAppointments(appts);
    setDailyTotal(total);
    setWeeklyTotals(weekly);
  }, [barber, isAdvanced]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const scheduled = appointments.filter(a => a.status === 'scheduled');
  const nextAppt = scheduled[0];
  const today = new Date().toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  const noShowRate = appointments.length > 0
    ? Math.round((appointments.filter(a => a.status === 'no_show').length / appointments.length) * 100)
    : 0;

  return (
    <View style={styles.container}>
      <ScreenHeader title="Home" screen="home" />
      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        <Text style={styles.date}>{today}</Text>
        <Text style={styles.greeting}>Hey, {barber?.name ?? 'Barber'}</Text>

        {/* Stats Row */}
        <View style={styles.statsRow}>
          <View style={styles.statCard}>
            <Text style={styles.statValue}>{scheduled.length}</Text>
            <Text style={styles.statLabel}>Appointments</Text>
          </View>
          <View style={styles.statCard}>
            <Text style={styles.statValue}>${dailyTotal.toFixed(0)}</Text>
            <Text style={styles.statLabel}>Today's Earnings</Text>
          </View>
        </View>

        {/* Advanced extras */}
        {isAdvanced && (
          <View style={styles.advancedSection}>
            <Text style={styles.sectionTitle}>This Week</Text>
            <View style={styles.sparklineRow}>
              {weeklyTotals.length > 0
                ? weeklyTotals.map((d) => (
                    <View key={d.date} style={styles.sparkBar}>
                      <View
                        style={[
                          styles.sparkFill,
                          { height: Math.max(4, (d.total / Math.max(...weeklyTotals.map(x => x.total), 1)) * 60) }
                        ]}
                      />
                      <Text style={styles.sparkLabel}>{d.date.slice(5)}</Text>
                    </View>
                  ))
                : <Text style={styles.empty}>No earnings data this week</Text>
              }
            </View>
            <View style={styles.statsRow}>
              <View style={styles.statCard}>
                <Text style={styles.statValue}>{noShowRate}%</Text>
                <Text style={styles.statLabel}>No-show Rate</Text>
              </View>
            </View>
          </View>
        )}

        {/* Next Appointment */}
        <Text style={styles.sectionTitle}>Next Appointment</Text>
        {nextAppt ? (
          <View style={styles.apptCard}>
            <Text style={styles.apptTime}>{nextAppt.start_time}</Text>
            <Text style={styles.apptClient}>
              {nextAppt.walk_in ? 'Walk-in' : nextAppt.client_id ? 'Client' : 'Unknown'}
            </Text>
          </View>
        ) : (
          <Text style={styles.empty}>No upcoming appointments today</Text>
        )}

        {/* Quick Actions */}
        <Text style={styles.sectionTitle}>Quick Actions</Text>
        <View style={styles.actionsGrid}>
          <TouchableOpacity style={styles.actionBtn} onPress={() => onNavigate('appointments')}>
            <Text style={styles.actionIcon}>📅</Text>
            <Text style={styles.actionLabel}>View Schedule</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => onNavigate('walkin')}>
            <Text style={styles.actionIcon}>⚡</Text>
            <Text style={styles.actionLabel}>Walk-in</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.actionBtn} onPress={() => onNavigate('capture')}>
            <Text style={styles.actionIcon}>📷</Text>
            <Text style={styles.actionLabel}>Capture</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  scroll: { flex: 1 },
  content: { padding: spacing.md, gap: spacing.md },
  date: { color: colors.textMuted, fontSize: 13 },
  greeting: { color: colors.text, fontSize: 26, fontWeight: '800', marginBottom: spacing.sm },
  statsRow: { flexDirection: 'row', gap: spacing.sm },
  statCard: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
  },
  statValue: { color: colors.primary, fontSize: 28, fontWeight: '800' },
  statLabel: { color: colors.textMuted, fontSize: 12, marginTop: 2 },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: '700', marginTop: spacing.sm },
  apptCard: {
    backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
    flexDirection: 'row', alignItems: 'center', gap: spacing.md,
  },
  apptTime: { color: colors.primary, fontSize: 18, fontWeight: '700', minWidth: 60 },
  apptClient: { color: colors.text, fontSize: 16 },
  empty: { color: colors.textMuted, fontSize: 14 },
  actionsGrid: { flexDirection: 'row', gap: spacing.sm },
  actionBtn: {
    flex: 1, backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, alignItems: 'center', borderWidth: 1,
    borderColor: colors.border, minHeight: minTapTarget + 20,
    justifyContent: 'center', gap: 6,
  },
  actionIcon: { fontSize: 24 },
  actionLabel: { color: colors.textMuted, fontSize: 12, textAlign: 'center' },
  advancedSection: { gap: spacing.sm },
  sparklineRow: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 4,
    backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border,
    height: 100,
  },
  sparkBar: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', gap: 4 },
  sparkFill: { width: '80%', backgroundColor: colors.primary, borderRadius: 2 },
  sparkLabel: { color: colors.textDim, fontSize: 9 },
});

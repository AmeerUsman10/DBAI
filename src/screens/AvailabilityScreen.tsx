import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  TextInput, Share, Alert
} from 'react-native';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import {
  getAvailability, saveAvailability, getBlockedDates,
  addBlockedDate, removeBlockedDate, getBookingSettings, saveBookingSettings
} from '../database/db';
import type { Availability, BlockedDate, BookingSettings } from '../types';

const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

export function AvailabilityScreen() {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('availability'));
  const storeCurrency = useStore((s) => s.currency);
  const [availability, setAvailability] = useState<Availability[]>([]);
  const [blockedDates, setBlockedDates] = useState<BlockedDate[]>([]);
  const [settings, setSettings] = useState<BookingSettings | null>(null);
  const [blockingDate, setBlockingDate] = useState('');

  // Advanced settings form
  const [bufferMins, setBufferMins] = useState('0');
  const [requireDeposit, setRequireDeposit] = useState(false);
  const [depositAmount, setDepositAmount] = useState('0');
  const [cancelPolicy, setCancelPolicy] = useState('');
  const [reminderEnabled, setReminderEnabled] = useState(false);

  const load = useCallback(async () => {
    if (!barber) return;
    const [avail, blocked, s] = await Promise.all([
      getAvailability(barber.id),
      getBlockedDates(barber.id),
      getBookingSettings(barber.id),
    ]);
    setAvailability(avail);
    setBlockedDates(blocked);
    setSettings(s);
    if (s) {
      setBufferMins(String(s.buffer_minutes));
      setRequireDeposit(s.require_deposit);
      setDepositAmount(String(s.deposit_amount));
      setCancelPolicy(s.cancellation_policy_text ?? '');
      setReminderEnabled(s.reminder_enabled);
    }
  }, [barber]);

  useEffect(() => { load(); }, [load]);

  async function toggleDay(index: number) {
    if (!barber) return;
    const updated = availability.map((a) =>
      a.day_of_week === index ? { ...a, is_active: !a.is_active } : a
    );
    // If no record for this day yet, create one
    if (!updated.find(a => a.day_of_week === index)) {
      updated.push({
        id: `temp-${index}`,
        barber_id: barber.id,
        day_of_week: index,
        start_time: '09:00',
        end_time: '18:00',
        is_active: true,
      });
    }
    setAvailability(updated);
    await saveAvailability(updated.map(({ id, ...rest }) => rest));
  }

  async function blockDate() {
    if (!barber || !blockingDate.trim()) return;
    await addBlockedDate(barber.id, blockingDate.trim());
    setBlockingDate('');
    load();
  }

  async function unblockDate(dateId: string) {
    await removeBlockedDate(dateId);
    load();
  }

  async function saveAdvancedSettings() {
    if (!barber) return;
    await saveBookingSettings({
      barber_id: barber.id,
      buffer_minutes: parseInt(bufferMins) || 0,
      require_deposit: requireDeposit,
      deposit_amount: parseFloat(depositAmount) || 0,
      cancellation_policy_text: cancelPolicy.trim() || undefined,
      reminder_enabled: reminderEnabled,
      currency: settings?.currency ?? storeCurrency,
    });
    Alert.alert('Saved', 'Settings updated.');
  }

  const bookingLink = barber
    ? `https://book.barberapp.co/${barber.id}`
    : '';

  function shareLink() {
    if (!bookingLink) return;
    Share.share({ message: `Book with me: ${bookingLink}` });
  }

  const isDayActive = (dayIndex: number) =>
    availability.find(a => a.day_of_week === dayIndex)?.is_active ?? false;

  return (
    <View style={styles.container}>
      <ScreenHeader title="Availability" screen="availability" />
      <ScrollView contentContainerStyle={styles.content}>

        {/* Weekly grid */}
        <Text style={styles.sectionTitle}>Working Days</Text>
        <View style={styles.daysRow}>
          {DAYS.map((day, i) => (
            <TouchableOpacity
              key={day}
              style={[styles.dayBtn, isDayActive(i) && styles.dayBtnActive]}
              onPress={() => toggleDay(i)}
            >
              <Text style={[styles.dayLabel, isDayActive(i) && styles.dayLabelActive]}>{day}</Text>
            </TouchableOpacity>
          ))}
        </View>

        {/* Booking link */}
        <Text style={styles.sectionTitle}>Booking Link</Text>
        <View style={styles.linkCard}>
          <Text style={styles.linkText} numberOfLines={1}>{bookingLink}</Text>
          <TouchableOpacity style={styles.shareBtn} onPress={shareLink}>
            <Text style={styles.shareBtnText}>Share</Text>
          </TouchableOpacity>
        </View>
        <TouchableOpacity
          style={styles.copyBtn}
          onPress={() => Alert.alert('Copied', bookingLink)}
        >
          <Text style={styles.copyBtnText}>Copy Link</Text>
        </TouchableOpacity>

        {/* Block a date */}
        <Text style={styles.sectionTitle}>Block a Date</Text>
        <View style={styles.blockRow}>
          <TextInput
            style={[styles.input, { flex: 1 }]}
            value={blockingDate}
            onChangeText={setBlockingDate}
            placeholder="YYYY-MM-DD"
            placeholderTextColor={colors.textDim}
          />
          <TouchableOpacity style={styles.blockBtn} onPress={blockDate}>
            <Text style={styles.blockBtnText}>Block</Text>
          </TouchableOpacity>
        </View>

        {blockedDates.length > 0 && (
          <View style={styles.blockedList}>
            {blockedDates.map(bd => (
              <View key={bd.id} style={styles.blockedRow}>
                <Text style={styles.blockedDate}>{bd.date}</Text>
                {bd.reason ? <Text style={styles.blockedReason}>{bd.reason}</Text> : null}
                <TouchableOpacity onPress={() => unblockDate(bd.id)} style={styles.unblockBtn}>
                  <Text style={styles.unblockText}>Remove</Text>
                </TouchableOpacity>
              </View>
            ))}
          </View>
        )}

        {/* Advanced settings */}
        {isAdvanced && (
          <View style={styles.advancedSection}>
            <Text style={styles.sectionTitle}>Advanced Settings</Text>

            <Text style={styles.fieldLabel}>Buffer Between Appointments (minutes)</Text>
            <TextInput
              style={styles.input}
              value={bufferMins}
              onChangeText={setBufferMins}
              keyboardType="number-pad"
              placeholder="0"
              placeholderTextColor={colors.textDim}
            />

            <View style={styles.toggleRow}>
              <Text style={styles.fieldLabel}>Require Deposit</Text>
              <TouchableOpacity
                style={[styles.toggle, requireDeposit && styles.toggleActive]}
                onPress={() => setRequireDeposit(v => !v)}
              >
                <Text style={styles.toggleText}>{requireDeposit ? 'ON' : 'OFF'}</Text>
              </TouchableOpacity>
            </View>

            {requireDeposit && (
              <TextInput
                style={styles.input}
                value={depositAmount}
                onChangeText={setDepositAmount}
                keyboardType="decimal-pad"
                placeholder="Deposit amount"
                placeholderTextColor={colors.textDim}
              />
            )}

            <Text style={styles.fieldLabel}>Cancellation Policy</Text>
            <TextInput
              style={[styles.input, { height: 80 }]}
              value={cancelPolicy}
              onChangeText={setCancelPolicy}
              multiline
              placeholder="e.g. 24h notice required"
              placeholderTextColor={colors.textDim}
            />

            <View style={styles.toggleRow}>
              <Text style={styles.fieldLabel}>24hr SMS Reminder to Client</Text>
              <TouchableOpacity
                style={[styles.toggle, reminderEnabled && styles.toggleActive]}
                onPress={() => setReminderEnabled(v => !v)}
              >
                <Text style={styles.toggleText}>{reminderEnabled ? 'ON' : 'OFF'}</Text>
              </TouchableOpacity>
            </View>

            <TouchableOpacity style={styles.saveBtn} onPress={saveAdvancedSettings}>
              <Text style={styles.saveBtnText}>Save Settings</Text>
            </TouchableOpacity>
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: 40 },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: '700', marginTop: spacing.sm },
  daysRow: { flexDirection: 'row', gap: spacing.xs },
  dayBtn: {
    flex: 1, minHeight: minTapTarget, backgroundColor: colors.surface,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    alignItems: 'center', justifyContent: 'center',
  },
  dayBtnActive: { backgroundColor: colors.primary, borderColor: colors.primary },
  dayLabel: { color: colors.textMuted, fontSize: 12, fontWeight: '600' },
  dayLabelActive: { color: '#000' },
  linkCard: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface,
    borderRadius: radius.md, borderWidth: 1, borderColor: colors.border,
    padding: spacing.md, gap: spacing.sm,
  },
  linkText: { flex: 1, color: colors.textMuted, fontSize: 13 },
  shareBtn: {
    backgroundColor: colors.primary, paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm, borderRadius: radius.sm,
    minHeight: minTapTarget, justifyContent: 'center',
  },
  shareBtnText: { color: '#000', fontWeight: '700', fontSize: 13 },
  copyBtn: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.primary, alignItems: 'center',
    minHeight: minTapTarget, justifyContent: 'center',
  },
  copyBtnText: { color: colors.primary, fontWeight: '600' },
  blockRow: { flexDirection: 'row', gap: spacing.sm },
  input: {
    backgroundColor: colors.surface, color: colors.text, padding: spacing.md,
    borderRadius: radius.md, fontSize: 15, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget,
  },
  blockBtn: {
    backgroundColor: colors.error, paddingHorizontal: spacing.md,
    borderRadius: radius.md, alignItems: 'center', justifyContent: 'center',
    minHeight: minTapTarget,
  },
  blockBtnText: { color: '#fff', fontWeight: '700' },
  blockedList: { gap: spacing.xs },
  blockedRow: {
    flexDirection: 'row', alignItems: 'center', backgroundColor: colors.surface,
    borderRadius: radius.sm, padding: spacing.md, borderWidth: 1,
    borderColor: colors.border, gap: spacing.sm,
  },
  blockedDate: { color: colors.text, fontWeight: '600', flex: 1 },
  blockedReason: { color: colors.textMuted, fontSize: 12, flex: 1 },
  unblockBtn: { padding: spacing.xs },
  unblockText: { color: colors.error, fontSize: 13 },
  advancedSection: { gap: spacing.sm },
  fieldLabel: { color: colors.textMuted, fontSize: 13 },
  toggleRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  toggle: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radius.sm, borderWidth: 1, borderColor: colors.border,
    minWidth: 60, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  toggleActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  toggleText: { color: colors.text, fontWeight: '600', fontSize: 13 },
  saveBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', marginTop: spacing.sm,
    minHeight: minTapTarget, justifyContent: 'center',
  },
  saveBtnText: { color: '#000', fontWeight: '700', fontSize: 15 },
});

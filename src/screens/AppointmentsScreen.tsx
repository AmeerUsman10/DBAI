import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  Modal, TextInput, Alert, RefreshControl, KeyboardAvoidingView, Platform
} from 'react-native';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { FAB } from '../components/FAB';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import {
  getAppointmentsForDate, createAppointment,
  updateAppointmentStatus, getServices
} from '../database/db';
import { formatPrice } from '../lib/currency';
import type { Appointment, Service, Status } from '../types';

const todayStr = () => new Date().toISOString().split('T')[0];

const STATUS_COLORS: Record<Status, string> = {
  scheduled: colors.primary,
  completed: colors.success,
  cancelled: colors.error,
  no_show: colors.warning,
};

export function AppointmentsScreen() {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('appointments'));
  const currency = useStore((s) => s.currency);
  const [appointments, setAppointments] = useState<Appointment[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [selectedDate, setSelectedDate] = useState(todayStr());
  const [refreshing, setRefreshing] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedAppt, setSelectedAppt] = useState<Appointment | null>(null);

  // Add appointment form
  const [clientName, setClientName] = useState('');
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [startTime, setStartTime] = useState('10:00');
  const [notes, setNotes] = useState('');

  const load = useCallback(async () => {
    if (!barber) return;
    const [appts, svcs] = await Promise.all([
      getAppointmentsForDate(barber.id, selectedDate),
      getServices(barber.id),
    ]);
    setAppointments(appts);
    setServices(svcs);
    if (svcs.length > 0 && !selectedService) setSelectedService(svcs[0]);
  }, [barber, selectedDate]);

  useEffect(() => { load(); }, [load]);

  const onRefresh = async () => { setRefreshing(true); await load(); setRefreshing(false); };

  function addMinutes(time: string, mins: number) {
    const [h, m] = time.split(':').map(Number);
    const total = h * 60 + m + mins;
    return `${String(Math.floor(total / 60)).padStart(2, '0')}:${String(total % 60).padStart(2, '0')}`;
  }

  async function addAppointment(walkIn: boolean) {
    if (!barber || !selectedService) return;
    const duration = selectedService.duration_minutes ?? 30;
    await createAppointment({
      barber_id: barber.id,
      client_id: undefined,
      service_id: selectedService.id,
      date: selectedDate,
      start_time: startTime,
      end_time: addMinutes(startTime, duration),
      status: 'scheduled',
      walk_in: walkIn,
      notes: notes.trim() || undefined,
    });
    setShowAddModal(false);
    setClientName('');
    setNotes('');
    load();
  }

  async function updateStatus(appt: Appointment, status: Status) {
    await updateAppointmentStatus(appt.id, status);
    setSelectedAppt(null);
    load();
  }

  const dateLabel = new Date(selectedDate + 'T12:00:00').toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  });

  return (
    <View style={styles.container}>
      <ScreenHeader title="Appointments" screen="appointments" />

      {/* Date selector */}
      <View style={styles.dateRow}>
        <TouchableOpacity
          style={styles.dateArrow}
          onPress={() => {
            const d = new Date(selectedDate + 'T12:00:00');
            d.setDate(d.getDate() - 1);
            setSelectedDate(d.toISOString().split('T')[0]);
          }}
        >
          <Text style={styles.arrowText}>{'<'}</Text>
        </TouchableOpacity>
        <Text style={styles.dateLabel}>{dateLabel}</Text>
        <TouchableOpacity
          style={styles.dateArrow}
          onPress={() => {
            const d = new Date(selectedDate + 'T12:00:00');
            d.setDate(d.getDate() + 1);
            setSelectedDate(d.toISOString().split('T')[0]);
          }}
        >
          <Text style={styles.arrowText}>{'>'}</Text>
        </TouchableOpacity>
      </View>

      <ScrollView
        style={styles.scroll}
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />}
      >
        {appointments.length === 0 && (
          <Text style={styles.empty}>No appointments for this day</Text>
        )}
        {appointments.map(appt => {
          const svc = services.find(s => s.id === appt.service_id);
          return (
            <TouchableOpacity
              key={appt.id}
              style={styles.slotCard}
              onPress={() => setSelectedAppt(appt)}
            >
              <View style={[styles.statusBar, { backgroundColor: STATUS_COLORS[appt.status] }]} />
              <View style={styles.slotInfo}>
                <Text style={styles.slotTime}>{appt.start_time} – {appt.end_time}</Text>
                <Text style={styles.slotClient}>
                  {appt.walk_in ? 'Walk-in' : 'Client'}
                  {isAdvanced && appt.walk_in && <Text style={styles.walkInBadge}> Walk-in</Text>}
                </Text>
                {svc && <Text style={styles.slotService}>{svc.name} · {formatPrice(svc.price, currency)}</Text>}
                {appt.notes ? <Text style={styles.slotNotes}>{appt.notes}</Text> : null}
              </View>
              <View style={styles.slotRight}>
                <Text style={[styles.statusDot, { color: STATUS_COLORS[appt.status] }]}>●</Text>
                <Text style={styles.statusLabel}>{appt.status.replace('_', ' ')}</Text>
              </View>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      <FAB label="+ Add" onPress={() => setShowAddModal(true)} />

      {/* Add Appointment Modal */}
      <Modal visible={showAddModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
            <View style={styles.modalSheet}>
              <Text style={styles.modalTitle}>New Appointment</Text>

              <Text style={styles.fieldLabel}>Service</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: spacing.sm }}>
                <View style={{ flexDirection: 'row', gap: spacing.xs }}>
                  {services.map(svc => (
                    <TouchableOpacity
                      key={svc.id}
                      style={[styles.chip, selectedService?.id === svc.id && styles.chipActive]}
                      onPress={() => setSelectedService(svc)}
                    >
                      <Text style={[styles.chipText, selectedService?.id === svc.id && styles.chipTextActive]}>
                        {svc.name} — {formatPrice(svc.price, currency)}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </View>
              </ScrollView>

              <Text style={styles.fieldLabel}>Start Time (HH:MM)</Text>
              <TextInput
                style={styles.input}
                value={startTime}
                onChangeText={setStartTime}
                placeholder="10:00"
                placeholderTextColor={colors.textDim}
              />

              <Text style={styles.fieldLabel}>Notes (optional)</Text>
              <TextInput
                style={[styles.input, { height: 72 }]}
                value={notes}
                onChangeText={setNotes}
                multiline
                placeholder="Any notes..."
                placeholderTextColor={colors.textDim}
              />

              <View style={styles.modalButtons}>
                <TouchableOpacity style={styles.walkInBtn} onPress={() => addAppointment(true)}>
                  <Text style={styles.walkInBtnText}>Walk-in (No client)</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.addBtn} onPress={() => addAppointment(false)}>
                  <Text style={styles.addBtnText}>Add Appointment</Text>
                </TouchableOpacity>
              </View>

              <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowAddModal(false)}>
                <Text style={styles.cancelText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </KeyboardAvoidingView>
        </View>
      </Modal>

      {/* Slot Action Modal */}
      <Modal visible={!!selectedAppt} animationType="fade" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>Update Status</Text>
            {selectedAppt && (
              <View style={{ gap: spacing.sm }}>
                {(['completed', 'cancelled', 'no_show', 'scheduled'] as Status[]).map(status => (
                  <TouchableOpacity
                    key={status}
                    style={[styles.statusBtn, { borderColor: STATUS_COLORS[status] }]}
                    onPress={() => updateStatus(selectedAppt, status)}
                  >
                    <Text style={[styles.statusBtnText, { color: STATUS_COLORS[status] }]}>
                      {status.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            )}
            <TouchableOpacity style={styles.cancelBtn} onPress={() => setSelectedAppt(null)}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  dateRow: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: spacing.lg, paddingVertical: spacing.sm,
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  dateArrow: { padding: spacing.sm, minWidth: minTapTarget, alignItems: 'center' },
  arrowText: { color: colors.primary, fontSize: 18, fontWeight: '700' },
  dateLabel: { color: colors.text, fontSize: 16, fontWeight: '600' },
  scroll: { flex: 1 },
  content: { padding: spacing.md, gap: spacing.sm, paddingBottom: 100 },
  empty: { color: colors.textMuted, textAlign: 'center', marginTop: spacing.xl },
  slotCard: {
    backgroundColor: colors.surface, borderRadius: radius.md,
    flexDirection: 'row', overflow: 'hidden',
    borderWidth: 1, borderColor: colors.border, minHeight: minTapTarget + 16,
  },
  statusBar: { width: 4 },
  slotInfo: { flex: 1, padding: spacing.md, gap: 2 },
  slotTime: { color: colors.primary, fontSize: 14, fontWeight: '700' },
  slotClient: { color: colors.text, fontSize: 16, fontWeight: '600' },
  slotService: { color: colors.textMuted, fontSize: 13 },
  slotNotes: { color: colors.textDim, fontSize: 12, fontStyle: 'italic' },
  slotRight: { padding: spacing.sm, alignItems: 'center', justifyContent: 'center', gap: 2 },
  statusDot: { fontSize: 10 },
  statusLabel: { color: colors.textMuted, fontSize: 10 },
  walkInBadge: { color: colors.warning, fontSize: 12 },
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl, padding: spacing.lg, gap: spacing.sm,
  },
  modalTitle: { color: colors.text, fontSize: 20, fontWeight: '700', marginBottom: spacing.sm },
  fieldLabel: { color: colors.textMuted, fontSize: 13 },
  input: {
    backgroundColor: colors.surfaceAlt, color: colors.text, padding: spacing.md,
    borderRadius: radius.md, fontSize: 16, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget,
  },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border,
    backgroundColor: colors.surfaceAlt, minHeight: minTapTarget, justifyContent: 'center',
  },
  chipActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  chipText: { color: colors.textMuted, fontWeight: '600' },
  chipTextActive: { color: colors.text },
  modalButtons: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.sm },
  walkInBtn: {
    flex: 1, padding: spacing.md, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.primary, alignItems: 'center',
    minHeight: minTapTarget, justifyContent: 'center',
  },
  walkInBtnText: { color: colors.primary, fontWeight: '600' },
  addBtn: {
    flex: 1, padding: spacing.md, borderRadius: radius.md,
    backgroundColor: colors.primary, alignItems: 'center',
    minHeight: minTapTarget, justifyContent: 'center',
  },
  addBtnText: { color: '#000', fontWeight: '700' },
  statusBtn: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1,
    alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  statusBtnText: { fontWeight: '600', fontSize: 15 },
  cancelBtn: {
    padding: spacing.md, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  cancelText: { color: colors.textMuted, fontSize: 15 },
});

import React, { useEffect, useState, useCallback } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, Modal } from 'react-native';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import { getDailyTotal, getWeeklyTotals, createVisit, getServices } from '../database/db';
import { formatPrice } from '../lib/currency';
import type { PaymentMethod, Service } from '../types';

const METHODS: PaymentMethod[] = ['cash', 'card', 'wallet'];

export function PaymentsScreen() {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('payments'));
  const currency = useStore((s) => s.currency);
  const [dailyTotal, setDailyTotal] = useState(0);
  const [weeklyTotals, setWeeklyTotals] = useState<{ date: string; total: number }[]>([]);
  const [services, setServices] = useState<Service[]>([]);
  const [showRecordModal, setShowRecordModal] = useState(false);
  const [selectedService, setSelectedService] = useState<Service | null>(null);
  const [selectedMethod, setSelectedMethod] = useState<PaymentMethod>('cash');

  const today = new Date().toISOString().split('T')[0];

  const load = useCallback(async () => {
    if (!barber) return;
    const [total, weekly, svcs] = await Promise.all([
      getDailyTotal(barber.id, today),
      isAdvanced ? getWeeklyTotals(barber.id) : Promise.resolve([]),
      getServices(barber.id),
    ]);
    setDailyTotal(total);
    setWeeklyTotals(weekly);
    setServices(svcs);
    if (svcs.length > 0 && !selectedService) setSelectedService(svcs[0]);
  }, [barber, isAdvanced, today]);

  useEffect(() => { load(); }, [load]);

  async function recordPayment() {
    if (!barber || !selectedService) return;
    await createVisit({
      barber_id: barber.id,
      date: today,
      service_id: selectedService.id,
      amount_paid: selectedService.price,
      payment_method: selectedMethod,
    });
    setShowRecordModal(false);
    load();
  }

  const weeklyMax = Math.max(...weeklyTotals.map(w => w.total), 1);

  return (
    <View style={styles.container}>
      <ScreenHeader title="Payments" screen="payments" />
      <ScrollView contentContainerStyle={styles.content}>

        <View style={styles.heroCard}>
          <Text style={styles.heroLabel}>Today's Earnings</Text>
          <Text style={styles.heroValue}>{formatPrice(dailyTotal, currency)}</Text>
        </View>

        <TouchableOpacity style={styles.recordBtn} onPress={() => setShowRecordModal(true)}>
          <Text style={styles.recordBtnText}>Record Payment</Text>
        </TouchableOpacity>

        {isAdvanced && (
          <View style={styles.advancedSection}>
            <Text style={styles.sectionTitle}>Last 7 Days</Text>
            <View style={styles.barChart}>
              {weeklyTotals.map(d => (
                <View key={d.date} style={styles.barWrapper}>
                  <Text style={styles.barValue}>{formatPrice(d.total, currency)}</Text>
                  <View style={[styles.bar, { height: Math.max(4, (d.total / weeklyMax) * 100) }]} />
                  <Text style={styles.barDate}>{d.date.slice(5)}</Text>
                </View>
              ))}
            </View>

            <Text style={styles.sectionTitle}>Revenue by Service</Text>
            {services.map(svc => (
              <View key={svc.id} style={styles.serviceRevRow}>
                <Text style={styles.serviceRevName}>{svc.name}</Text>
                <Text style={styles.serviceRevPrice}>{formatPrice(svc.price, currency)}/cut</Text>
              </View>
            ))}
          </View>
        )}
      </ScrollView>

      <Modal visible={showRecordModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>Record Payment</Text>

            <Text style={styles.fieldLabel}>Service</Text>
            <View style={styles.chipRow}>
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

            {selectedService && (
              <View style={styles.totalRow}>
                <Text style={styles.totalLabel}>Total</Text>
                <Text style={styles.totalValue}>{formatPrice(selectedService.price, currency)}</Text>
              </View>
            )}

            <Text style={styles.fieldLabel}>Payment Method</Text>
            <View style={styles.methodRow}>
              {METHODS.map(m => (
                <TouchableOpacity
                  key={m}
                  style={[styles.methodBtn, selectedMethod === m && styles.methodBtnActive]}
                  onPress={() => setSelectedMethod(m)}
                >
                  <Text style={[styles.methodLabel, selectedMethod === m && styles.methodLabelActive]}>
                    {m.charAt(0).toUpperCase() + m.slice(1)}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity style={styles.confirmBtn} onPress={recordPayment}>
              <Text style={styles.confirmText}>Confirm Payment</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowRecordModal(false)}>
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
  content: { padding: spacing.md, gap: spacing.md, paddingBottom: 40 },
  heroCard: {
    backgroundColor: colors.surface, borderRadius: radius.lg,
    padding: spacing.xl, alignItems: 'center', borderWidth: 1, borderColor: colors.border,
  },
  heroLabel: { color: colors.textMuted, fontSize: 14 },
  heroValue: { color: colors.primary, fontSize: 48, fontWeight: '800', marginTop: 4 },
  recordBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  recordBtnText: { color: '#000', fontWeight: '700', fontSize: 16 },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: '700' },
  advancedSection: { gap: spacing.md },
  barChart: {
    flexDirection: 'row', alignItems: 'flex-end', gap: 4,
    backgroundColor: colors.surface, borderRadius: radius.md,
    padding: spacing.md, borderWidth: 1, borderColor: colors.border, height: 160,
  },
  barWrapper: { flex: 1, alignItems: 'center', justifyContent: 'flex-end', gap: 4 },
  barValue: { color: colors.textDim, fontSize: 9 },
  bar: { width: '70%', backgroundColor: colors.primary, borderRadius: 3 },
  barDate: { color: colors.textDim, fontSize: 9 },
  serviceRevRow: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    padding: spacing.md, backgroundColor: colors.surface, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border,
  },
  serviceRevName: { color: colors.text, fontSize: 14 },
  serviceRevPrice: { color: colors.primary, fontSize: 14, fontWeight: '600' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl, padding: spacing.lg, gap: spacing.sm,
  },
  modalTitle: { color: colors.text, fontSize: 20, fontWeight: '700', marginBottom: spacing.sm },
  fieldLabel: { color: colors.textMuted, fontSize: 13 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget, justifyContent: 'center',
  },
  chipActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  chipText: { color: colors.textMuted, fontWeight: '600' },
  chipTextActive: { color: colors.text },
  totalRow: { flexDirection: 'row', justifyContent: 'space-between', padding: spacing.sm },
  totalLabel: { color: colors.textMuted, fontSize: 16 },
  totalValue: { color: colors.primary, fontSize: 22, fontWeight: '800' },
  methodRow: { flexDirection: 'row', gap: spacing.sm },
  methodBtn: {
    flex: 1, padding: spacing.md, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, alignItems: 'center',
    minHeight: minTapTarget, justifyContent: 'center',
  },
  methodBtnActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  methodLabel: { color: colors.textMuted, fontWeight: '600' },
  methodLabelActive: { color: colors.text },
  confirmBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  confirmText: { color: '#000', fontWeight: '700', fontSize: 15 },
  cancelBtn: { padding: spacing.md, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center' },
  cancelText: { color: colors.textMuted, fontSize: 15 },
});

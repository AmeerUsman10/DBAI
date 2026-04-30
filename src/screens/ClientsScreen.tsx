import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  TextInput, Modal, Alert
} from 'react-native';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { FAB } from '../components/FAB';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import { getClients, searchClients, createClient, getVisitsForClient, updateClient } from '../database/db';
import type { Client, Visit } from '../types';

export function ClientsScreen() {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('clients'));
  const [clients, setClients] = useState<Client[]>([]);
  const [query, setQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [selectedClient, setSelectedClient] = useState<Client | null>(null);
  const [clientVisits, setClientVisits] = useState<Visit[]>([]);

  // Add client form
  const [newName, setNewName] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [newNotes, setNewNotes] = useState('');

  const load = useCallback(async () => {
    if (!barber) return;
    const result = query.trim()
      ? await searchClients(barber.id, query.trim())
      : await getClients(barber.id);
    setClients(result);
  }, [barber, query]);

  useEffect(() => { load(); }, [load]);

  async function openClient(client: Client) {
    setSelectedClient(client);
    if (isAdvanced) {
      const visits = await getVisitsForClient(client.id);
      setClientVisits(visits);
    }
  }

  async function addClient() {
    if (!barber || !newName.trim() || !newPhone.trim()) {
      Alert.alert('Required', 'Name and phone are required.');
      return;
    }
    await createClient({
      barber_id: barber.id,
      name: newName.trim(),
      phone: newPhone.trim(),
      notes: newNotes.trim() || undefined,
    });
    setNewName(''); setNewPhone(''); setNewNotes('');
    setShowAddModal(false);
    load();
  }

  const totalSpend = clientVisits.reduce((sum, v) => sum + v.amount_paid, 0);
  const lastVisit = clientVisits[0]?.date;

  return (
    <View style={styles.container}>
      <ScreenHeader title="Clients" screen="clients" />

      <View style={styles.searchRow}>
        <TextInput
          style={styles.searchInput}
          value={query}
          onChangeText={setQuery}
          placeholder="Search by name or phone"
          placeholderTextColor={colors.textDim}
          clearButtonMode="while-editing"
        />
      </View>

      <FlatList
        data={clients}
        keyExtractor={c => c.id}
        contentContainerStyle={styles.list}
        renderItem={({ item }) => (
          <TouchableOpacity style={styles.clientCard} onPress={() => openClient(item)}>
            <View style={styles.clientAvatar}>
              <Text style={styles.avatarLetter}>{item.name[0].toUpperCase()}</Text>
            </View>
            <View style={styles.clientInfo}>
              <Text style={styles.clientName}>{item.name}</Text>
              <Text style={styles.clientPhone}>{item.phone}</Text>
            </View>
          </TouchableOpacity>
        )}
        ListEmptyComponent={<Text style={styles.empty}>No clients yet</Text>}
      />

      <FAB label="+ Client" onPress={() => setShowAddModal(true)} />

      {/* Add Client Modal */}
      <Modal visible={showAddModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>New Client</Text>

            <Text style={styles.fieldLabel}>Name *</Text>
            <TextInput
              style={styles.input}
              value={newName}
              onChangeText={setNewName}
              placeholder="Full name"
              placeholderTextColor={colors.textDim}
            />

            <Text style={styles.fieldLabel}>Phone *</Text>
            <TextInput
              style={styles.input}
              value={newPhone}
              onChangeText={setNewPhone}
              placeholder="Phone number"
              placeholderTextColor={colors.textDim}
              keyboardType="phone-pad"
            />

            <Text style={styles.fieldLabel}>Notes</Text>
            <TextInput
              style={[styles.input, { height: 80 }]}
              value={newNotes}
              onChangeText={setNewNotes}
              placeholder="Optional notes"
              placeholderTextColor={colors.textDim}
              multiline
            />

            <TouchableOpacity style={styles.addBtn} onPress={addClient}>
              <Text style={styles.addBtnText}>Add Client</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowAddModal(false)}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Client Detail Modal */}
      <Modal visible={!!selectedClient} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            {selectedClient && (
              <>
                <Text style={styles.modalTitle}>{selectedClient.name}</Text>
                <Text style={styles.detailPhone}>{selectedClient.phone}</Text>
                {selectedClient.notes ? (
                  <Text style={styles.detailNotes}>{selectedClient.notes}</Text>
                ) : null}

                {isAdvanced && (
                  <View style={styles.advancedStats}>
                    <View style={styles.advStatRow}>
                      <Text style={styles.advStatLabel}>Visits</Text>
                      <Text style={styles.advStatValue}>{clientVisits.length}</Text>
                    </View>
                    <View style={styles.advStatRow}>
                      <Text style={styles.advStatLabel}>Total Spend</Text>
                      <Text style={styles.advStatValue}>${totalSpend.toFixed(2)}</Text>
                    </View>
                    {lastVisit && (
                      <View style={styles.advStatRow}>
                        <Text style={styles.advStatLabel}>Last Visit</Text>
                        <Text style={styles.advStatValue}>{lastVisit}</Text>
                      </View>
                    )}
                    {clientVisits.length > 0 && (
                      <View style={styles.visitHistory}>
                        <Text style={styles.fieldLabel}>Visit History</Text>
                        {clientVisits.slice(0, 5).map(v => (
                          <View key={v.id} style={styles.visitRow}>
                            <Text style={styles.visitDate}>{v.date}</Text>
                            <Text style={styles.visitAmount}>${v.amount_paid}</Text>
                            <Text style={styles.visitMethod}>{v.payment_method}</Text>
                          </View>
                        ))}
                      </View>
                    )}
                  </View>
                )}

                <TouchableOpacity style={styles.addBtn}>
                  <Text style={styles.addBtnText}>Book Again</Text>
                </TouchableOpacity>
                <TouchableOpacity style={styles.cancelBtn} onPress={() => setSelectedClient(null)}>
                  <Text style={styles.cancelText}>Close</Text>
                </TouchableOpacity>
              </>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  searchRow: { padding: spacing.md, borderBottomWidth: 1, borderBottomColor: colors.border },
  searchInput: {
    backgroundColor: colors.surface, color: colors.text, padding: spacing.md,
    borderRadius: radius.md, fontSize: 15, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget,
  },
  list: { padding: spacing.md, gap: spacing.sm, paddingBottom: 100 },
  clientCard: {
    backgroundColor: colors.surface, borderRadius: radius.md,
    flexDirection: 'row', alignItems: 'center', padding: spacing.md,
    borderWidth: 1, borderColor: colors.border, gap: spacing.md,
    minHeight: minTapTarget + 8,
  },
  clientAvatar: {
    width: 44, height: 44, borderRadius: 22,
    backgroundColor: colors.primaryDim, alignItems: 'center', justifyContent: 'center',
  },
  avatarLetter: { color: colors.text, fontSize: 18, fontWeight: '700' },
  clientInfo: { flex: 1 },
  clientName: { color: colors.text, fontSize: 16, fontWeight: '600' },
  clientPhone: { color: colors.textMuted, fontSize: 13, marginTop: 2 },
  empty: { color: colors.textMuted, textAlign: 'center', marginTop: spacing.xl },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
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
  addBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  addBtnText: { color: '#000', fontWeight: '700', fontSize: 15 },
  cancelBtn: { padding: spacing.md, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center' },
  cancelText: { color: colors.textMuted, fontSize: 15 },
  detailPhone: { color: colors.textMuted, fontSize: 15, marginBottom: spacing.sm },
  detailNotes: { color: colors.text, fontSize: 14, marginBottom: spacing.sm },
  advancedStats: { gap: spacing.sm },
  advStatRow: { flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 4 },
  advStatLabel: { color: colors.textMuted, fontSize: 14 },
  advStatValue: { color: colors.text, fontSize: 14, fontWeight: '600' },
  visitHistory: { gap: 4, marginTop: spacing.sm },
  visitRow: { flexDirection: 'row', gap: spacing.md, paddingVertical: 4 },
  visitDate: { color: colors.textMuted, fontSize: 13, flex: 1 },
  visitAmount: { color: colors.primary, fontSize: 13, fontWeight: '600' },
  visitMethod: { color: colors.textDim, fontSize: 13 },
});

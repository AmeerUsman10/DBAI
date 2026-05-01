import React, { useState, useEffect } from 'react';
import {
  View, Text, TouchableOpacity, ScrollView, StyleSheet,
  TextInput, Alert, Image
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import { updateBarber, getServices, createService, updateService, deleteService, getBookingSettings, saveBookingSettings } from '../database/db';
import { CURRENCIES } from '../lib/currency';
import type { Service, Currency } from '../types';

export function SettingsScreen() {
  const barber = useStore((s) => s.barber);
  const setBarber = useStore((s) => s.setBarber);
  const storeCurrency = useStore((s) => s.currency);
  const setCurrency = useStore((s) => s.setCurrency);

  const [name, setName] = useState(barber?.name ?? '');
  const [shopName, setShopName] = useState(barber?.shop_name ?? '');
  const [phone, setPhone] = useState(barber?.phone ?? '');
  const [photoUri, setPhotoUri] = useState(barber?.profile_photo_url);
  const [services, setServicesList] = useState<Service[]>([]);
  const [selectedCurrency, setSelectedCurrency] = useState<Currency>(storeCurrency);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    if (barber && !loaded) {
      Promise.all([
        getServices(barber.id),
        getBookingSettings(barber.id),
      ]).then(([svcs, settings]) => {
        setServicesList(svcs);
        if (settings?.currency) {
          setSelectedCurrency(settings.currency);
          setCurrency(settings.currency);
        }
        setLoaded(true);
      });
    }
  }, [barber, loaded]);

  async function saveProfile() {
    if (!barber) return;
    if (!name.trim() || !shopName.trim() || !phone.trim()) {
      Alert.alert('Required', 'All fields are required.');
      return;
    }
    await updateBarber(barber.id, {
      name: name.trim(), shop_name: shopName.trim(),
      phone: phone.trim(), profile_photo_url: photoUri,
    });
    setBarber({ ...barber, name: name.trim(), shop_name: shopName.trim(), phone: phone.trim(), profile_photo_url: photoUri });
    Alert.alert('Saved', 'Profile updated.');
  }

  async function saveCurrency() {
    if (!barber) return;
    setCurrency(selectedCurrency);
    const existing = await getBookingSettings(barber.id);
    await saveBookingSettings({
      barber_id: barber.id,
      buffer_minutes: existing?.buffer_minutes ?? 0,
      require_deposit: existing?.require_deposit ?? false,
      deposit_amount: existing?.deposit_amount ?? 0,
      cancellation_policy_text: existing?.cancellation_policy_text,
      reminder_enabled: existing?.reminder_enabled ?? false,
      currency: selectedCurrency,
    });
    Alert.alert('Saved', `Currency set to ${selectedCurrency}.`);
  }

  async function pickPhoto() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: true, aspect: [1, 1], quality: 0.8,
    });
    if (!result.canceled) setPhotoUri(result.assets[0].uri);
  }

  async function addService() {
    if (!barber) return;
    const svc = await createService({ barber_id: barber.id, name: 'New Service', price: 0, duration_minutes: 30 });
    setServicesList(s => [...s, svc]);
  }

  function updateSvcLocal(id: string, field: 'name' | 'price', value: string) {
    setServicesList(s => s.map(svc =>
      svc.id === id ? { ...svc, [field]: field === 'price' ? parseFloat(value) || 0 : value } : svc
    ));
  }

  async function saveSvc(svc: Service) {
    await updateService(svc.id, { name: svc.name, price: svc.price });
  }

  async function removeSvc(id: string) {
    Alert.alert('Delete Service', 'Remove this service?', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: async () => {
        await deleteService(id);
        setServicesList(s => s.filter(svc => svc.id !== id));
      }},
    ]);
  }

  return (
    <View style={styles.container}>
      <ScreenHeader title="Settings" screen="settings" showAdvancedToggle={false} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">

        <Text style={styles.sectionTitle}>Profile</Text>
        <TouchableOpacity style={styles.photoBtn} onPress={pickPhoto}>
          {photoUri
            ? <Image source={{ uri: photoUri }} style={styles.photo} />
            : <View style={styles.photoPlaceholder}><Text style={styles.photoPlaceholderText}>Photo</Text></View>
          }
        </TouchableOpacity>
        <Text style={styles.fieldLabel}>Name</Text>
        <TextInput style={styles.input} value={name} onChangeText={setName} placeholderTextColor={colors.textDim} />
        <Text style={styles.fieldLabel}>Shop Name</Text>
        <TextInput style={styles.input} value={shopName} onChangeText={setShopName} placeholderTextColor={colors.textDim} />
        <Text style={styles.fieldLabel}>Phone</Text>
        <TextInput style={styles.input} value={phone} onChangeText={setPhone} keyboardType="phone-pad" placeholderTextColor={colors.textDim} />
        <TouchableOpacity style={styles.saveBtn} onPress={saveProfile}>
          <Text style={styles.saveBtnText}>Save Profile</Text>
        </TouchableOpacity>

        <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Currency</Text>
        <View style={styles.currencyGrid}>
          {CURRENCIES.map(c => (
            <TouchableOpacity
              key={c.code}
              style={[styles.currencyChip, selectedCurrency === c.code && styles.currencyChipActive]}
              onPress={() => setSelectedCurrency(c.code)}
            >
              <Text style={[styles.currencySymbol, selectedCurrency === c.code && styles.currencySymbolActive]}>
                {c.symbol}
              </Text>
              <Text style={[styles.currencyCode, selectedCurrency === c.code && styles.currencyCodeActive]}>
                {c.code}
              </Text>
              <Text style={styles.currencyLabel}>{c.label}</Text>
            </TouchableOpacity>
          ))}
        </View>
        <TouchableOpacity style={styles.saveBtn} onPress={saveCurrency}>
          <Text style={styles.saveBtnText}>Save Currency</Text>
        </TouchableOpacity>

        <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Services Menu</Text>
        {services.map(svc => (
          <View key={svc.id} style={styles.serviceRow}>
            <TextInput
              style={[styles.input, { flex: 1 }]}
              value={svc.name}
              onChangeText={v => updateSvcLocal(svc.id, 'name', v)}
              onBlur={() => saveSvc(svc)}
              placeholderTextColor={colors.textDim}
            />
            <TextInput
              style={[styles.input, styles.priceInput]}
              value={String(svc.price)}
              onChangeText={v => updateSvcLocal(svc.id, 'price', v)}
              onBlur={() => saveSvc(svc)}
              keyboardType="decimal-pad"
              placeholderTextColor={colors.textDim}
            />
            <TouchableOpacity onPress={() => removeSvc(svc.id)} style={styles.deleteBtn}>
              <Text style={styles.deleteText}>✕</Text>
            </TouchableOpacity>
          </View>
        ))}
        <TouchableOpacity style={styles.addRowBtn} onPress={addService}>
          <Text style={styles.addRowText}>+ Add Service</Text>
        </TouchableOpacity>

        <Text style={[styles.sectionTitle, { marginTop: spacing.lg }]}>Data</Text>
        <TouchableOpacity
          style={styles.exportBtn}
          onPress={() => Alert.alert('Export', 'CSV export coming in next update.')}
        >
          <Text style={styles.exportBtnText}>Export Data (CSV)</Text>
        </TouchableOpacity>

        <TouchableOpacity
          style={styles.logoutBtn}
          onPress={() => Alert.alert('Logout', 'Are you sure?', [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Logout', style: 'destructive' },
          ])}
        >
          <Text style={styles.logoutText}>Logout</Text>
        </TouchableOpacity>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: colors.bg },
  content: { padding: spacing.md, gap: spacing.sm, paddingBottom: 40 },
  sectionTitle: { color: colors.text, fontSize: 16, fontWeight: '700', marginTop: spacing.sm },
  fieldLabel: { color: colors.textMuted, fontSize: 13, marginTop: spacing.sm },
  input: {
    backgroundColor: colors.surface, color: colors.text, padding: spacing.md,
    borderRadius: radius.md, fontSize: 15, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget,
  },
  saveBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', marginTop: spacing.md, minHeight: minTapTarget, justifyContent: 'center',
  },
  saveBtnText: { color: '#000', fontWeight: '700', fontSize: 15 },
  photoBtn: { alignSelf: 'center', marginVertical: spacing.sm },
  photo: { width: 88, height: 88, borderRadius: 44 },
  photoPlaceholder: {
    width: 88, height: 88, borderRadius: 44, backgroundColor: colors.surface,
    borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center',
  },
  photoPlaceholderText: { color: colors.textMuted, fontSize: 12 },
  currencyGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.sm },
  currencyChip: {
    width: '47%', backgroundColor: colors.surface, borderRadius: radius.md,
    borderWidth: 1, borderColor: colors.border, padding: spacing.md, gap: 2,
  },
  currencyChipActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  currencySymbol: { color: colors.textMuted, fontSize: 20, fontWeight: '700' },
  currencySymbolActive: { color: colors.text },
  currencyCode: { color: colors.textMuted, fontSize: 13, fontWeight: '600' },
  currencyCodeActive: { color: colors.text },
  currencyLabel: { color: colors.textDim, fontSize: 11 },
  serviceRow: { flexDirection: 'row', gap: spacing.xs, alignItems: 'center' },
  priceInput: { width: 80 },
  deleteBtn: { padding: spacing.sm, minWidth: minTapTarget, alignItems: 'center' },
  deleteText: { color: colors.error, fontSize: 18 },
  addRowBtn: { padding: spacing.md, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center' },
  addRowText: { color: colors.primary, fontWeight: '600', fontSize: 15 },
  exportBtn: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.border, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  exportBtnText: { color: colors.text, fontWeight: '600' },
  logoutBtn: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.error, alignItems: 'center', marginTop: spacing.lg,
    minHeight: minTapTarget, justifyContent: 'center',
  },
  logoutText: { color: colors.error, fontWeight: '700', fontSize: 15 },
});

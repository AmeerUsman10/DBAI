import React, { useEffect, useState, useCallback } from 'react';
import {
  View, Text, TouchableOpacity, FlatList, StyleSheet,
  Image, Modal, Alert, Dimensions
} from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { useStore } from '../store/useStore';
import { ScreenHeader } from '../components/ScreenHeader';
import { FAB } from '../components/FAB';
import { colors, spacing, radius, minTapTarget } from '../theme/colors';
import { getPortfolioItems, createPortfolioItem, updatePortfolioVisibility } from '../database/db';
import type { PortfolioItem, StyleTag, Visibility } from '../types';

const STYLE_TAGS: StyleTag[] = ['fade', 'taper', 'curl', 'beard', 'color', 'other'];
const COLS = 2;
const CARD_SIZE = (Dimensions.get('window').width - spacing.md * 3) / COLS;

export function PortfolioScreen() {
  const barber = useStore((s) => s.barber);
  const isAdvanced = useStore((s) => s.isAdvanced('portfolio'));
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<PortfolioItem | null>(null);
  const [showBeforeOnCard, setShowBeforeOnCard] = useState(false);
  const [showUploadModal, setShowUploadModal] = useState(false);
  const [uploadUri, setUploadUri] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState<StyleTag>('fade');
  const [visibility, setVisibility] = useState<Visibility>('private');

  const load = useCallback(async () => {
    if (!barber) return;
    setItems(await getPortfolioItems(barber.id));
  }, [barber]);

  useEffect(() => { load(); }, [load]);

  async function pickPhoto() {
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (!result.canceled) {
      setUploadUri(result.assets[0].uri);
      setShowUploadModal(true);
    }
  }

  async function saveItem() {
    if (!barber || !uploadUri) return;
    await createPortfolioItem({
      barber_id: barber.id,
      photo_after_url: uploadUri,
      style_tag: selectedTag,
      visibility,
    });
    setShowUploadModal(false);
    setUploadUri(null);
    load();
  }

  async function toggleItemVisibility(item: PortfolioItem) {
    const next: Visibility = item.visibility === 'public' ? 'private' : 'public';
    await updatePortfolioVisibility(item.id, next);
    load();
  }

  const tagCounts = STYLE_TAGS.reduce((acc, tag) => {
    acc[tag] = items.filter(i => i.style_tag === tag).length;
    return acc;
  }, {} as Record<StyleTag, number>);

  return (
    <View style={styles.container}>
      <ScreenHeader title="Portfolio" screen="portfolio" />

      {isAdvanced && (
        <View style={styles.tagStats}>
          {STYLE_TAGS.map(tag => (
            <View key={tag} style={styles.tagStat}>
              <Text style={styles.tagCount}>{tagCounts[tag]}</Text>
              <Text style={styles.tagName}>{tag}</Text>
            </View>
          ))}
        </View>
      )}

      {isAdvanced && (
        <TouchableOpacity
          style={styles.beforeAfterToggle}
          onPress={() => setShowBeforeOnCard(v => !v)}
        >
          <Text style={styles.beforeAfterText}>
            Showing: {showBeforeOnCard ? 'Before' : 'After'}
          </Text>
        </TouchableOpacity>
      )}

      <FlatList
        data={items}
        keyExtractor={i => i.id}
        numColumns={COLS}
        contentContainerStyle={styles.grid}
        columnWrapperStyle={{ gap: spacing.md }}
        renderItem={({ item }) => {
          const photoUri = isAdvanced && showBeforeOnCard && item.photo_before_url
            ? item.photo_before_url
            : item.photo_after_url;
          return (
            <TouchableOpacity style={styles.card} onPress={() => setSelectedItem(item)}>
              <Image source={{ uri: photoUri }} style={styles.cardImage} resizeMode="cover" />
              <View style={styles.cardOverlay}>
                <Text style={styles.cardTag}>{item.style_tag}</Text>
                {isAdvanced && (
                  <Text style={[styles.visibilityBadge, item.visibility === 'public' && styles.publicBadge]}>
                    {item.visibility}
                  </Text>
                )}
              </View>
            </TouchableOpacity>
          );
        }}
        ListEmptyComponent={
          <View style={styles.emptyContainer}>
            <Text style={styles.empty}>No portfolio items yet</Text>
            <Text style={styles.emptySub}>Upload photos from your camera roll</Text>
          </View>
        }
      />

      <FAB label="+ Upload" onPress={pickPhoto} />

      {/* Upload modal */}
      <Modal visible={showUploadModal} animationType="slide" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <Text style={styles.modalTitle}>Add to Portfolio</Text>
            {uploadUri && <Image source={{ uri: uploadUri }} style={styles.previewImage} resizeMode="cover" />}

            <Text style={styles.fieldLabel}>Style Tag</Text>
            <View style={styles.tagRow}>
              {STYLE_TAGS.map(tag => (
                <TouchableOpacity
                  key={tag}
                  style={[styles.chip, selectedTag === tag && styles.chipActive]}
                  onPress={() => setSelectedTag(tag)}
                >
                  <Text style={[styles.chipText, selectedTag === tag && styles.chipTextActive]}>{tag}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <Text style={styles.fieldLabel}>Visibility</Text>
            <View style={styles.tagRow}>
              {(['private', 'public'] as Visibility[]).map(v => (
                <TouchableOpacity
                  key={v}
                  style={[styles.chip, visibility === v && styles.chipActive]}
                  onPress={() => setVisibility(v)}
                >
                  <Text style={[styles.chipText, visibility === v && styles.chipTextActive]}>{v}</Text>
                </TouchableOpacity>
              ))}
            </View>

            <TouchableOpacity style={styles.addBtn} onPress={saveItem}>
              <Text style={styles.addBtnText}>Save to Portfolio</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.cancelBtn} onPress={() => setShowUploadModal(false)}>
              <Text style={styles.cancelText}>Cancel</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Item detail modal */}
      <Modal visible={!!selectedItem} animationType="fade" transparent>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            {selectedItem && (
              <>
                <Image
                  source={{ uri: selectedItem.photo_after_url }}
                  style={styles.detailImage}
                  resizeMode="cover"
                />
                <Text style={styles.modalTitle}>{selectedItem.style_tag}</Text>
                <Text style={styles.detailDate}>{selectedItem.created_at.split('T')[0]}</Text>

                {isAdvanced && (
                  <TouchableOpacity
                    style={styles.visibilityBtn}
                    onPress={() => { toggleItemVisibility(selectedItem); setSelectedItem(null); }}
                  >
                    <Text style={styles.visibilityBtnText}>
                      Make {selectedItem.visibility === 'public' ? 'Private' : 'Public'}
                    </Text>
                  </TouchableOpacity>
                )}

                <TouchableOpacity style={styles.cancelBtn} onPress={() => setSelectedItem(null)}>
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
  grid: { padding: spacing.md, gap: spacing.md, paddingBottom: 100 },
  card: {
    width: CARD_SIZE, height: CARD_SIZE, borderRadius: radius.md,
    overflow: 'hidden', backgroundColor: colors.surface,
  },
  cardImage: { width: '100%', height: '100%' },
  cardOverlay: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    backgroundColor: 'rgba(0,0,0,0.55)', padding: spacing.sm,
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
  },
  cardTag: { color: colors.text, fontSize: 11, fontWeight: '600', textTransform: 'capitalize' },
  visibilityBadge: {
    fontSize: 10, color: colors.textMuted,
    backgroundColor: colors.surface, paddingHorizontal: 4,
    paddingVertical: 1, borderRadius: 4,
  },
  publicBadge: { color: colors.success },
  emptyContainer: { padding: spacing.xl, alignItems: 'center', gap: spacing.sm },
  empty: { color: colors.textMuted, fontSize: 16 },
  emptySub: { color: colors.textDim, fontSize: 13 },
  tagStats: {
    flexDirection: 'row', paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm, gap: spacing.sm, flexWrap: 'wrap',
    borderBottomWidth: 1, borderBottomColor: colors.border,
  },
  tagStat: { alignItems: 'center', minWidth: 44 },
  tagCount: { color: colors.primary, fontSize: 18, fontWeight: '700' },
  tagName: { color: colors.textMuted, fontSize: 11, textTransform: 'capitalize' },
  beforeAfterToggle: {
    margin: spacing.md, marginBottom: 0,
    padding: spacing.sm, borderRadius: radius.sm,
    borderWidth: 1, borderColor: colors.border, alignSelf: 'flex-start',
    minHeight: minTapTarget, justifyContent: 'center',
  },
  beforeAfterText: { color: colors.primary, fontSize: 13, fontWeight: '600' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'flex-end' },
  modalSheet: {
    backgroundColor: colors.surface, borderTopLeftRadius: radius.xl,
    borderTopRightRadius: radius.xl, padding: spacing.lg, gap: spacing.sm,
  },
  modalTitle: { color: colors.text, fontSize: 20, fontWeight: '700' },
  previewImage: { width: '100%', height: 200, borderRadius: radius.md },
  detailImage: { width: '100%', height: 240, borderRadius: radius.md },
  detailDate: { color: colors.textMuted, fontSize: 13 },
  fieldLabel: { color: colors.textMuted, fontSize: 13 },
  tagRow: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  chip: {
    paddingHorizontal: spacing.md, paddingVertical: spacing.sm,
    borderRadius: radius.xl, borderWidth: 1, borderColor: colors.border,
    minHeight: minTapTarget, justifyContent: 'center',
  },
  chipActive: { borderColor: colors.primary, backgroundColor: colors.primaryDim },
  chipText: { color: colors.textMuted, fontWeight: '600', textTransform: 'capitalize' },
  chipTextActive: { color: colors.text },
  addBtn: {
    backgroundColor: colors.primary, padding: spacing.md, borderRadius: radius.md,
    alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center',
  },
  addBtnText: { color: '#000', fontWeight: '700', fontSize: 15 },
  cancelBtn: { padding: spacing.md, alignItems: 'center', minHeight: minTapTarget, justifyContent: 'center' },
  cancelText: { color: colors.textMuted, fontSize: 15 },
  visibilityBtn: {
    padding: spacing.md, borderRadius: radius.md, borderWidth: 1,
    borderColor: colors.primary, alignItems: 'center',
    minHeight: minTapTarget, justifyContent: 'center',
  },
  visibilityBtnText: { color: colors.primary, fontWeight: '600' },
});

import { create } from 'zustand';
import type { Barber, Service, Client, Appointment, SyncStatus, Currency } from '../types';

interface AppStore {
  barber: Barber | null;
  services: Service[];
  clients: Client[];
  todayAppointments: Appointment[];
  syncStatus: SyncStatus;
  currency: Currency;
  advancedMode: Record<string, boolean>;

  setBarber: (b: Barber | null) => void;
  setServices: (s: Service[]) => void;
  setClients: (c: Client[]) => void;
  setTodayAppointments: (a: Appointment[]) => void;
  setSyncStatus: (s: SyncStatus) => void;
  setCurrency: (c: Currency) => void;
  toggleAdvancedMode: (screen: string) => void;
  isAdvanced: (screen: string) => boolean;
}

export const useStore = create<AppStore>((set, get) => ({
  barber: null,
  services: [],
  clients: [],
  todayAppointments: [],
  syncStatus: 'offline',
  currency: 'PKR',
  advancedMode: {},

  setBarber: (barber) => set({ barber }),
  setServices: (services) => set({ services }),
  setClients: (clients) => set({ clients }),
  setTodayAppointments: (todayAppointments) => set({ todayAppointments }),
  setSyncStatus: (syncStatus) => set({ syncStatus }),
  setCurrency: (currency) => set({ currency }),
  toggleAdvancedMode: (screen) =>
    set((s) => ({ advancedMode: { ...s.advancedMode, [screen]: !s.advancedMode[screen] } })),
  isAdvanced: (screen) => get().advancedMode[screen] ?? false,
}));

"use client";

import React, { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import api from '@/lib/api';
import { User, Organization } from '@/types';

interface AuthContextType {
  user: User | null;
  organizations: Organization[];
  activeOrganization: Organization | null;
  isLoading: boolean;
  login: (token: string) => Promise<void>;
  logout: () => void;
  setActiveOrganization: (org: Organization) => void;
  fetchData: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [activeOrganization, setActiveOrganization] = useState<Organization | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchData = async () => {
    setIsLoading(true);
    try {
      const token = localStorage.getItem('token');
      if (!token) {
        setIsLoading(false);
        return;
      }

      // Fetch user and organizations in parallel
      const [userRes, orgsRes] = await Promise.all([
        api.get<User>('/auth/me'),
        api.get<Organization[]>('/organizations/')
      ]);

      setUser(userRes.data);
      setOrganizations(orgsRes.data);
      
      // Auto-select first org if none selected
      if (orgsRes.data.length > 0 && !activeOrganization) {
        setActiveOrganization(orgsRes.data[0]);
      }
    } catch (error) {
      console.error('Error fetching auth data:', error);
      setUser(null);
      setOrganizations([]);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  const login = async (token: string) => {
    localStorage.setItem('token', token);
    await fetchData();
  };

  const logout = () => {
    localStorage.removeItem('token');
    setUser(null);
    setOrganizations([]);
    setActiveOrganization(null);
    if (typeof window !== 'undefined') {
      window.location.href = '/login';
    }
  };

  return (
    <AuthContext.Provider value={{
      user,
      organizations,
      activeOrganization,
      isLoading,
      login,
      logout,
      setActiveOrganization,
      fetchData
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}

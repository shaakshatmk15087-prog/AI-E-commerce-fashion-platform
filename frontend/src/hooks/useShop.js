import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { shopApi } from "../services/api.js";
import { useAuth } from "../context/AuthContext.jsx";

export function useCart() {
  const { user } = useAuth();
  return useQuery({ queryKey: ["cart"], queryFn: shopApi.cart, enabled: !!user, select: (d) => d.cart });
}

export function useCartActions() {
  const qc = useQueryClient();
  const done = () => qc.invalidateQueries({ queryKey: ["cart"] });
  return {
    add: useMutation({ mutationFn: ({ variantId, qty }) => shopApi.cartAdd(variantId, qty), onSuccess: done }),
    set: useMutation({ mutationFn: ({ id, qty }) => shopApi.cartSet(id, qty), onSuccess: done }),
    remove: useMutation({ mutationFn: (id) => shopApi.cartRemove(id), onSuccess: done }),
  };
}

export function useWishlistIds() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["wishlist"], queryFn: shopApi.wishlist, enabled: !!user });
  return { ids: new Set((q.data?.products || []).map((p) => p.id)), products: q.data?.products, isLoading: q.isLoading };
}

export function useToggleWishlist() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, on }) => (on ? shopApi.wishRemove(id) : shopApi.wishAdd(id)),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["wishlist"] }),
  });
}
